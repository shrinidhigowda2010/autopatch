"""FixPilot Assistant turn runner: Gemini tool loop + silent rule-based fallback."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterator
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.agent.tools import TOOL_DECLARATIONS, execute_tool, project_context, tool_label
from app.config import settings
from app.llm.gemini import GeminiError, mark_failed, model_plan
from app.models import Bug, Project
from app.services import latest_scan
from sqlalchemy import select

log = logging.getLogger(__name__)

EventEmit = Callable[[dict], None]

_LANG = {
    "en": "Answer in clear English.",
    "kn": "Answer in Kannada (ಕನ್ನಡ). Keep code identifiers in English.",
    "hi": "Answer in Hindi (हिन्दी). Keep code identifiers in English.",
}


def run_assistant_turn(
    session: Session,
    project: Project,
    history: list[dict[str, str]],
    user_message: str,
    language: str = "en",
    emit: EventEmit | None = None,
) -> dict:
    """
    Produce an assistant reply with optional tool steps and patch cards.
    emit() receives SSE-shaped dicts: token | tool | done | error
    """

    def send(event: dict) -> None:
        if emit:
            emit(event)

    if settings.gemini_configured:
        try:
            return _run_gemini(session, project, history, user_message, language, send)
        except Exception as exc:  # noqa: BLE001
            log.warning("assistant gemini failed, using fallback: %s", exc)
    return _run_fallback(session, project, user_message, language, send)


def stream_tokens(text: str, send: EventEmit, chunk: int = 24) -> None:
    for i in range(0, len(text), chunk):
        send({"type": "token", "text": text[i : i + chunk]})


def _system_prompt(language: str, context: str) -> str:
    lang = _LANG.get(language, _LANG["en"])
    return (
        "You are FixPilot Assistant, a careful coding agent. "
        "You help the user understand bugs, tests, and proposed fixes in THEIR uploaded project. "
        "Never claim you applied a patch. Patches require the human to click Approve. "
        "Use tools when you need file contents, bug details, diffs, search, or test summaries. "
        f"{lang}\n\nProject context:\n{context}"
    )


def _run_gemini(
    session: Session,
    project: Project,
    history: list[dict[str, str]],
    user_message: str,
    language: str,
    send: EventEmit,
) -> dict:
    context = project_context(session, project)
    contents: list[dict[str, Any]] = []
    for item in history[-12:]:
        role = "user" if item.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": item.get("content") or ""}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    tools = [{"function_declarations": TOOL_DECLARATIONS}]
    tool_steps: list[dict] = []
    patch_cards: list[dict] = []

    for _round in range(5):
        payload = _gemini_chat(
            contents,
            system=_system_prompt(language, context),
            tools=tools,
        )
        candidate = (payload.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts")) or []
        function_calls = [p.get("functionCall") for p in parts if p.get("functionCall")]
        text_bits = [p.get("text") for p in parts if p.get("text")]

        if function_calls:
            # Model wants tools — execute and continue.
            model_content = {"role": "model", "parts": parts}
            contents.append(model_content)
            response_parts = []
            for call in function_calls:
                name = str(call.get("name") or "")
                raw_args = call.get("args") or {}
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {}
                label = tool_label(name, raw_args)
                send({"type": "tool", "name": name, "label": label, "status": "running", "args": raw_args})
                result, card = execute_tool(session, project, name, raw_args)
                step = {
                    "name": name,
                    "label": label,
                    "status": "done",
                    "args": raw_args,
                    "result_preview": _preview(result),
                }
                if name == "run_tests" and isinstance(result, dict) and "passed" in result:
                    step["label"] = (
                        f"{result.get('passed', 0)} passed, {result.get('failed', 0)} failed"
                        if result.get("status") != "none"
                        else label
                    )
                tool_steps.append(step)
                send({"type": "tool", **step})
                if card:
                    patch_cards.append(card)
                    send({"type": "patch", "patch": card})
                response_parts.append(
                    {
                        "functionResponse": {
                            "name": name,
                            "response": result if isinstance(result, dict) else {"result": result},
                        }
                    }
                )
            contents.append({"role": "user", "parts": response_parts})
            continue

        answer = "\n".join(bit for bit in text_bits if bit).strip()
        if not answer:
            answer = "I looked at the project context. Ask me about a specific bug, file, or test."
        stream_tokens(answer, send)
        send({"type": "done", "tool_steps": tool_steps, "patches": patch_cards})
        return {"content": answer, "tool_steps": tool_steps, "patches": patch_cards}

    # Exceeded tool rounds
    answer = "I gathered tool results but need a clearer question to finish. Try asking about one bug or file."
    stream_tokens(answer, send)
    send({"type": "done", "tool_steps": tool_steps, "patches": patch_cards})
    return {"content": answer, "tool_steps": tool_steps, "patches": patch_cards}


def _gemini_chat(contents: list[dict], system: str, tools: list | None = None) -> dict:
    if not settings.gemini_configured:
        raise GeminiError("GEMINI_API_KEY is not set")
    body: dict[str, Any] = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.3},
    }
    if tools:
        body["tools"] = tools
    last = "no model answered"
    for model, _attempts in model_plan():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            with httpx.Client(timeout=max(settings.gemini_timeout_s, 30.0)) as client:
                response = client.post(url, params={"key": settings.gemini_api_key}, json=body)
        except httpx.HTTPError as exc:
            mark_failed(model)
            last = f"{model}: {exc.__class__.__name__}"
            continue
        if response.status_code < 400:
            return response.json()
        mark_failed(model)
        last = f"{model} returned {response.status_code}"
    raise GeminiError(last)


def _preview(result: dict) -> str:
    try:
        raw = json.dumps(result, ensure_ascii=False)
    except TypeError:
        raw = str(result)
    return raw[:280]


def _run_fallback(
    session: Session,
    project: Project,
    user_message: str,
    language: str,
    send: EventEmit,
) -> dict:
    """Rule-based answers from stored findings when Gemini is unavailable."""
    text = user_message.lower()
    scan = latest_scan(session, project.id)
    bugs = list(session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all()) if scan else []
    tool_steps: list[dict] = []
    patches: list[dict] = []

    if any(word in text for word in ("bug", "find", "scan", "issue", "error")) and bugs:
        step = {"name": "search_code", "label": "Reviewing scan findings...", "status": "done", "args": {}, "result_preview": f"{len(bugs)} findings"}
        tool_steps.append(step)
        send({"type": "tool", **step})
        lines = [f"I found {len(bugs)} finding(s) in this project:"]
        for bug in bugs[:8]:
            lines.append(f"- **{bug.title}** (`{bug.file}:{bug.line}`, {bug.severity}) — {bug.student_explanation or bug.root_cause}")
        answer = "\n".join(lines)
    elif "test" in text:
        from app.agent.tools import execute_tool

        step_label = "Running tests..."
        send({"type": "tool", "name": "run_tests", "label": step_label, "status": "running", "args": {}})
        result, _ = execute_tool(session, project, "run_tests", {})
        label = (
            f"{result.get('passed', 0)} passed, {result.get('failed', 0)} failed"
            if result.get("status") != "none"
            else "No test run yet"
        )
        step = {"name": "run_tests", "label": label, "status": "done", "args": {}, "result_preview": _preview(result)}
        tool_steps.append(step)
        send({"type": "tool", **step})
        answer = (
            f"Latest test status: **{result.get('status')}**. "
            f"Regression passed: {result.get('regression_passed')}. "
            f"Generated tests passed: {result.get('generated_passed')}."
        )
    elif "explain" in text or "why" in text:
        bug = bugs[0] if bugs else None
        bug_id_match = re.search(r"\b([a-f0-9]{12})\b", user_message)
        if bug_id_match:
            found = session.get(Bug, bug_id_match.group(1))
            if found and found.project_id == project.id:
                bug = found
        if bug:
            step = {
                "name": "explain_bug",
                "label": f"Explaining bug {bug.id}...",
                "status": "done",
                "args": {"bug_id": bug.id},
                "result_preview": bug.title,
            }
            tool_steps.append(step)
            send({"type": "tool", **step})
            answer = (
                f"**{bug.title}** in `{bug.file}:{bug.line}`.\n\n"
                f"{bug.student_explanation or bug.root_cause}\n\n"
                f"What triggers it: {bug.trigger or 'See the report for details.'}"
            )
        else:
            answer = "I do not have scan findings yet. Run a scan, then ask me to explain a bug."
    elif "fix" in text or "patch" in text or "safe" in text:
        bug = bugs[0] if bugs else None
        if bug:
            result, card = execute_tool(session, project, "propose_fix", {"bug_id": bug.id})
            step = {
                "name": "propose_fix",
                "label": f"Proposing fix for {bug.id}...",
                "status": "done",
                "args": {"bug_id": bug.id},
                "result_preview": _preview(result),
            }
            tool_steps.append(step)
            send({"type": "tool", **step})
            if card:
                patches.append(card)
                send({"type": "patch", "patch": card})
            answer = (
                f"Here is the proposed fix for **{bug.title}**. "
                "It is not applied until you click Approve on the diff card."
            )
        else:
            answer = "No bugs with patches are available yet. Run a scan first."
    else:
        answer = (
            f"I can help with project **{project.name}**: find bugs, explain root causes, "
            "show diffs, and summarize tests. Try: “Find all bugs in this project”."
        )

    if language == "kn":
        answer = "ಕನ್ನಡ ಸಾರಾಂಶ:\n" + answer
    elif language == "hi":
        answer = "हिन्दी सारांश:\n" + answer

    stream_tokens(answer, send)
    send({"type": "done", "tool_steps": tool_steps, "patches": patches})
    return {"content": answer, "tool_steps": tool_steps, "patches": patches}
