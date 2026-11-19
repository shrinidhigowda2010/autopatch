"""FixPilot Assistant: one chat turn.

1. Make sure the code has been scanned (static tools only, a few seconds).
2. Let Gemini answer with the findings already in its context. It gets a short
   per-call timeout, at most two models, and at most two rounds of tool calls
   before it has to answer.
3. If Gemini is unavailable or fails, build the answer from the real scan
   results: the bugs, why they happen, the suggested patch, and test results.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tools import TOOL_DECLARATIONS, execute_tool, project_context, tool_label
from app.config import settings
from app.llm.gemini import (
    COOLDOWN_S,
    GeminiError,
    chat_models,
    gemini_usable,
    google_error_text,
    mark_failed,
    mark_key_rejected,
)
from app.models import Bug, Patch, Project
from app.services import latest_scan, run_scan

log = logging.getLogger(__name__)

EventEmit = Callable[[dict], None]

MAX_TOOL_ROUNDS = 2
CHAT_TIMEOUT_S = 12.0
TIMEOUT_COOLDOWN_S = 60.0
TURN_BUDGET_S = 40.0

_LANG = {
    "en": "Answer in clear English.",
    "kn": "Answer in Kannada (ಕನ್ನಡ). Keep code identifiers in English.",
    "hi": "Answer in Hindi (हिन्दी). Keep code identifiers in English.",
}

MODE_HINTS = {
    "explain": "The user picked Explain mode: explain clearly and do not propose patches.",
    "fix": "The user picked Fix mode: find the cause and propose a minimal patch for approval.",
    "review": "The user picked Review mode: review for bugs, risks and edge cases, listed by severity.",
}

_ENGLISH_NOTE = {
    "kn": "\n\n_(AI ಅನುವಾದ ಈಗ ಲಭ್ಯವಿಲ್ಲ, ಆದ್ದರಿಂದ ಈ ಉತ್ತರ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿದೆ.)_",
    "hi": "\n\n_(AI अनुवाद अभी उपलब्ध नहीं है, इसलिए यह उत्तर अंग्रेज़ी में है।)_",
}


class _Turn:
    """What one reply has produced so far: streamed text, tool steps, patch cards."""

    def __init__(self, session: Session, project: Project, emit: EventEmit | None) -> None:
        self.session = session
        self.project = project
        self.emit = emit
        self.text = ""
        self.tool_steps: list[dict] = []
        self.patches: list[dict] = []

    def send(self, event: dict) -> None:
        if self.emit:
            self.emit(event)

    def stream(self, text: str) -> None:
        self.text += text
        for i in range(0, len(text), 48):
            self.send({"type": "token", "text": text[i : i + 48]})

    def step(self, name: str, label: str, args: dict | None = None, preview: str = "") -> None:
        step = {"name": name, "label": label, "status": "done", "args": args or {}, "result_preview": preview}
        self.tool_steps.append(step)
        self.send({"type": "tool", **step})

    def running(self, name: str, label: str) -> None:
        self.send({"type": "tool", "name": name, "label": label, "status": "running", "args": {}})

    def add_patch(self, card: dict | None) -> None:
        if card and all(item["patch_id"] != card["patch_id"] for item in self.patches):
            self.patches.append(card)
            self.send({"type": "patch", "patch": card})

    def finish(self) -> dict:
        self.send({"type": "done", "tool_steps": self.tool_steps, "patches": self.patches})
        return {"content": self.text.strip(), "tool_steps": self.tool_steps, "patches": self.patches}

    def bugs(self) -> list[Bug]:
        scan = latest_scan(self.session, self.project.id)
        if scan is None:
            return []
        rows = self.session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all()
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(rows, key=lambda bug: (bug.category == "style", order.get(bug.severity, 4), bug.file, bug.line))


def run_assistant_turn(
    session: Session,
    project: Project,
    history: list[dict[str, str]],
    user_message: str,
    language: str = "en",
    emit: EventEmit | None = None,
    mode: str = "auto",
    code_changed: bool = False,
) -> dict:
    """Produce one reply. emit() receives SSE-shaped dicts: token | tool | patch | done."""
    turn = _Turn(session, project, emit)
    ensure_scanned(turn, force=code_changed)

    if settings.gemini_configured and gemini_usable():
        try:
            return _run_gemini(turn, history, user_message, language, mode)
        except Exception as exc:  # noqa: BLE001 - any model failure falls back to the scan
            log.warning("assistant: Gemini did not answer, using scan results: %s", exc)
            if turn.text.strip():
                return turn.finish()  # keep the partial model answer the user already sees
    return _run_fallback(turn, user_message, language, mode)


def ensure_scanned(turn: _Turn, force: bool = False) -> None:
    """Run a quick static scan when the code is new or has never been scanned."""
    project = turn.project
    if project.file_count <= 0:
        return
    scan = latest_scan(turn.session, project.id)
    if scan is not None and scan.status == "complete" and not force:
        return
    turn.running("scan_project", "Scanning your code with pylint, pyflakes, bandit and FixPilot rules...")
    started = time.monotonic()
    scan = run_scan(turn.session, project, use_gemini=False)
    bugs = [bug for bug in turn.bugs() if bug.category != "style"]
    turn.step(
        "scan_project",
        f"Scan finished: {len(bugs)} bug{'s' if len(bugs) != 1 else ''} found",
        preview=f"{scan.status} in {time.monotonic() - started:.1f}s",
    )


# ------------------------------------------------------------------ Gemini


def _system_prompt(language: str, context: str, has_code: bool, mode: str) -> str:
    parts = [
        "You are FixPilot Assistant, a friendly, precise coding assistant for students and junior developers.",
        _LANG.get(language, _LANG["en"]),
        "Keep answers short and concrete. Use Markdown and code blocks.",
    ]
    if has_code:
        parts += [
            "The user's code and the latest static-scan findings are below. Answer from them directly:",
            "name each real bug with its file and line, why it happens, what input triggers it, and how to fix it.",
            "Ignore pure style notes unless asked. Use a tool only when you need something that is not below.",
            "Never claim a patch was applied: patches need the user to click Approve.",
        ]
    else:
        parts += [
            "No code is attached to this chat yet. Answer general programming questions directly.",
            "If the user wants code checked, ask them to paste it or attach a file or screenshot with the + button.",
        ]
    if mode in MODE_HINTS:
        parts.append(MODE_HINTS[mode])
    if has_code:
        parts.append(f"\nProject context:\n{context}")
    return "\n".join(parts)


def _run_gemini(turn: _Turn, history: list[dict[str, str]], user_message: str, language: str, mode: str) -> dict:
    has_code = turn.project.file_count > 0
    context = project_context(turn.session, turn.project) if has_code else ""
    system = _system_prompt(language, context, has_code, mode)
    contents: list[dict[str, Any]] = []
    for item in history[-12:]:
        role = "user" if item.get("role") == "user" else "model"
        if item.get("content"):
            contents.append({"role": role, "parts": [{"text": item["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    tools = [{"function_declarations": TOOL_DECLARATIONS}] if has_code else None
    deadline = time.monotonic() + TURN_BUDGET_S

    for round_no in range(MAX_TOOL_ROUNDS + 1):
        final = round_no == MAX_TOOL_ROUNDS or time.monotonic() > deadline - CHAT_TIMEOUT_S
        if final and round_no > 0:
            contents.append({"role": "user", "parts": [{"text": "Now answer my question using the tool results above."}]})
        text, calls, parts = _gemini_stream(contents, system, tools, allow_tools=not final, on_text=turn.stream)
        if calls and not final:
            contents.append({"role": "model", "parts": parts})
            contents.append({"role": "user", "parts": [_call_tool(turn, call) for call in calls]})
            continue
        if text.strip():
            return turn.finish()
        if final:
            break
    raise GeminiError("the model returned no answer")


def _call_tool(turn: _Turn, call: dict) -> dict:
    name = str(call.get("name") or "")
    args = call.get("args") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    label = tool_label(name, args)
    turn.send({"type": "tool", "name": name, "label": label, "status": "running", "args": args})
    result, card = execute_tool(turn.session, turn.project, name, args)
    if name == "run_tests" and isinstance(result, dict) and result.get("label"):
        label = result["label"]
    turn.step(name, label, args, _preview(result))
    turn.add_patch(card)
    return {"functionResponse": {"name": name, "response": result if isinstance(result, dict) else {"result": result}}}


def _gemini_stream(
    contents: list[dict],
    system: str,
    tools: list | None,
    allow_tools: bool,
    on_text: Callable[[str], None],
) -> tuple[str, list[dict], list[dict]]:
    """Stream one reply. Returns (text, function_calls, raw_parts). Tries at most two models."""
    body: dict[str, Any] = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1500},
    }
    if tools:
        body["tools"] = tools
        if not allow_tools:
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
    errors: list[str] = []
    for model in chat_models():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"
        streamed = False
        try:
            with (
                httpx.Client(timeout=httpx.Timeout(CHAT_TIMEOUT_S, connect=5.0)) as client,
                client.stream("POST", url, params={"key": settings.gemini_api_key, "alt": "sse"}, json=body) as resp,
            ):
                if resp.status_code in {401, 403}:
                    resp.read()
                    mark_key_rejected(google_error_text(resp))
                    raise GeminiError(f"{model} refused the API key ({resp.status_code})")
                if resp.status_code >= 400:
                    mark_failed(model)
                    errors.append(f"{model} returned {resp.status_code}")
                    continue
                texts: list[str] = []
                calls: list[dict] = []
                parts: list[dict] = []
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = json.loads(line[5:].strip() or "{}")
                    candidate = (chunk.get("candidates") or [{}])[0]
                    for part in (candidate.get("content") or {}).get("parts") or []:
                        parts.append(part)
                        if part.get("functionCall"):
                            calls.append(part["functionCall"])
                        elif part.get("text") and not part.get("thought"):
                            streamed = True
                            texts.append(part["text"])
                            on_text(part["text"])
                return "".join(texts), calls, parts
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            # A slow reply is often a one-off, so a timeout only benches the model briefly.
            mark_failed(model, TIMEOUT_COOLDOWN_S if isinstance(exc, httpx.TimeoutException) else COOLDOWN_S)
            errors.append(f"{model}: {exc.__class__.__name__}")
            if streamed:
                raise GeminiError("the model stopped mid-answer") from exc
    raise GeminiError("; ".join(errors) or "no model answered")


def _preview(result: Any) -> str:
    try:
        raw = json.dumps(result, ensure_ascii=False)
    except TypeError:
        raw = str(result)
    return raw[:280]


# ------------------------------------------------------------------ answers from the scan


def _intent(message: str, mode: str) -> str:
    if mode == "explain":
        return "explain"
    if mode == "fix":
        return "fix"
    if mode == "review":
        return "bugs"
    text = message.lower()
    if re.search(r"\b(run|rerun)\b.*\btests?\b|\btests?\b.*\b(pass|fail|run)|\bpytest\b|why did .* test", text):
        return "tests"
    if re.search(r"\b(fix|patch|repair|correct|diff|safe)\b", text):
        return "fix"
    if re.search(r"\b(explain|why|what does|how does|root cause|meaning)\b", text) and not re.search(r"\b(find|all bugs|any bugs)\b", text):
        return "explain"
    return "bugs"


def _run_fallback(turn: _Turn, message: str, language: str, mode: str) -> dict:
    if turn.project.file_count <= 0:
        turn.stream(_no_code_answer())
        return turn.finish()

    bugs = turn.bugs()
    real = [bug for bug in bugs if bug.category != "style"]
    intent = _intent(message, mode)
    if intent == "tests":
        answer = _answer_tests(turn)
    elif intent in {"fix", "explain"} and real:
        bug = _pick_bug(turn, real, message)
        answer = _answer_fix(turn, bug, language) if intent == "fix" else _answer_explain(turn, bug, language)
    else:
        answer = _answer_bugs(turn, bugs, language)
    turn.stream(answer + _ENGLISH_NOTE.get(language, ""))
    return turn.finish()


def _no_code_answer() -> str:
    return (
        "Paste the code you want me to check, either in a ``` block or right after your question, "
        "or attach a file or screenshot with the **+** button.\n\n"
        "I'll scan it with pylint, pyflakes, bandit and FixPilot's bug rules, explain each bug in plain words, "
        "and propose a patch you can approve. General questions without code need the AI model, "
        "which isn't reachable right now."
    )


def _pick_bug(turn: _Turn, real: list[Bug], message: str) -> Bug:
    match = re.search(r"\b([a-f0-9]{12})\b", message)
    if match:
        for bug in real:
            if bug.id == match.group(1):
                return bug
    lowered = message.lower()
    for bug in real:
        if bug.symbol and bug.symbol.lower() in lowered:
            return bug
    return real[0]


def _why(bug: Bug, language: str) -> str:
    if language == "kn" and bug.explanation_kn:
        return bug.explanation_kn
    if language == "hi" and bug.explanation_hi:
        return bug.explanation_hi
    return bug.root_cause or bug.student_explanation or bug.description


def _patch_for(turn: _Turn, bug: Bug) -> Patch | None:
    return turn.session.scalar(select(Patch).where(Patch.bug_id == bug.id).order_by(Patch.created_at.desc()))


def _short_diff(diff: str, limit: int = 16) -> str:
    lines = [line for line in diff.splitlines() if not line.startswith(("---", "+++"))]
    if len(lines) > limit:
        lines = lines[:limit] + ["…"]
    return "\n".join(lines)


def _bug_heading(bug: Bug) -> str:
    return (
        f"**{bug.title}**: `{bug.file}` line {bug.line} · {bug.severity} severity · "
        f"{round(bug.confidence * 100)}% confidence"
    )


def _answer_bugs(turn: _Turn, bugs: list[Bug], language: str) -> str:
    real = [bug for bug in bugs if bug.category != "style"]
    style = len(bugs) - len(real)
    files = turn.project.file_count
    turn.step("review_findings", f"Reviewing {len(real)} finding{'s' if len(real) != 1 else ''}", preview=f"{style} style notes")
    if not real:
        answer = (
            f"I scanned your code ({files} file{'s' if files != 1 else ''}) with pylint, pyflakes, bandit and "
            "FixPilot's bug rules and found **no bugs**."
        )
        if style:
            answer += f" There {'is' if style == 1 else 'are'} {style} style note{'s' if style != 1 else ''} (docstrings, formatting) that don't change behaviour."
        languages = json.loads(turn.project.languages_json or "[]")
        names = [item.get("name") if isinstance(item, dict) else str(item) for item in languages]
        if names and "Python" not in names:
            answer += " Deep checks and generated tests cover Python; for other languages a logic review needs the AI model."
        return answer

    lines = [f"I found **{len(real)} bug{'s' if len(real) != 1 else ''}** in your code:"]
    for index, bug in enumerate(real[:6], start=1):
        lines.append(f"\n**{index}.** {_bug_heading(bug)}")
        lines.append(f"- **Why:** {_why(bug, language)}")
        if bug.trigger:
            lines.append(f"- **Triggered by:** {bug.trigger}")
        patch = _patch_for(turn, bug)
        if patch and patch.diff:
            lines.append(f"- **Suggested fix:**\n\n```diff\n{_short_diff(patch.diff)}\n```")
            if len(turn.patches) < 3:
                _result, card = execute_tool(turn.session, turn.project, "propose_fix", {"bug_id": bug.id})
                turn.add_patch(card)
        else:
            lines.append("- **Suggested fix:** there is no automatic patch for this one; the explanation above shows what to change.")
    if len(real) > 6:
        lines.append(f"\n…and {len(real) - 6} more on the Scan page.")
    if style:
        lines.append(f"\nThere {'is' if style == 1 else 'are'} also {style} style note{'s' if style != 1 else ''} that don't affect behaviour.")
    if turn.patches:
        lines.append("\nNothing changes until you click **Approve** on a patch card. Ask me to *run the tests* to prove a fix.")
    return "\n".join(lines)


def _answer_explain(turn: _Turn, bug: Bug, language: str) -> str:
    turn.step("explain_bug", f"Explaining {bug.title}", {"bug_id": bug.id}, bug.title)
    lines = [_bug_heading(bug), "", _why(bug, language)]
    if bug.student_explanation and bug.student_explanation != bug.root_cause and language == "en":
        lines += ["", f"**In simple words:** {bug.student_explanation}"]
    if bug.trigger:
        lines += ["", f"**What triggers it:** {bug.trigger}"]
    if bug.impact:
        lines += ["", f"**Impact:** {bug.impact}"]
    if bug.snippet:
        lines += ["", f"```\n{bug.snippet.strip()[:800]}\n```"]
    patch = _patch_for(turn, bug)
    if patch and patch.diff:
        lines += ["", "**How to fix it:**", "", f"```diff\n{_short_diff(patch.diff)}\n```"]
    return "\n".join(lines)


def _answer_fix(turn: _Turn, bug: Bug, language: str) -> str:
    result, card = execute_tool(turn.session, turn.project, "propose_fix", {"bug_id": bug.id})
    turn.step("propose_fix", f"Proposing a fix for {bug.title}", {"bug_id": bug.id}, _preview(result))
    if card is None:
        return f"{_bug_heading(bug)}\n\n{_why(bug, language)}\n\nThere is no automatic patch for this bug yet, so it needs a manual change."
    turn.add_patch(card)
    return (
        f"Here is the fix for {_bug_heading(bug)}\n\n"
        f"**Why it's needed:** {_why(bug, language)}\n\n"
        f"```diff\n{_short_diff(card['diff'], 24)}\n```\n\n"
        "It is not applied until you click **Approve** on the card. After you approve, the tests re-run and the change "
        "rolls back by itself if anything breaks."
    )


def _answer_tests(turn: _Turn) -> str:
    turn.running("run_tests", "Running tests in the sandbox...")
    result, _card = execute_tool(turn.session, turn.project, "run_tests", {})
    turn.step("run_tests", result.get("label") or "Tests finished", preview=_preview(result))
    return result.get("message") or "Tests finished."
