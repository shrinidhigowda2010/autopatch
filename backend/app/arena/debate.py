"""AI Debate Room: a Fixer defends a patch, a Breaker attacks it, and a Judge decides.

Each turn is its own Gemini call, so the UI can show the debate as it happens.
When Gemini is unreachable, the arguments come from the test results instead.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator

from app.agent.redaction import redact_text
from app.arena.attack import rule_cases
from app.arena.context import PatchContext, find_target

log = logging.getLogger(__name__)

ROUNDS = 3
TURN_TIMEOUT_S = 15.0

_ROLE_BRIEF = {
    "fixer": (
        "You are Fixer, the engineer who wrote this patch. Defend it honestly. Answer the Breaker's "
        "last point directly, with concrete reasoning about the code. Admit a real hole in how this patch "
        "handles its own bug, but when the point belongs to another listed bug, say it has its own patch."
    ),
    "breaker": (
        "You are Breaker, a tough but professional reviewer. Attack the patch with ONE concrete edge case per turn "
        "(empty, None, negative, huge, unicode, wrong type, regressions for existing callers). Name the exact input "
        "and what you expect to go wrong. Stay on this patch's bug: other bugs listed below have their own patches. "
        "Do not repeat earlier attacks, and no insults."
    ),
}

_JUDGE = """You are Judge. Read the debate about this patch and decide.
Return JSON: {"verdict": "safe" | "needs_changes", "confidence": 0-100, "reason": "two sentences"}.
"safe" means the patch fixes its own bug without breaking anything that worked before.
Gaps that belong to other listed bugs, or wider hardening ideas, lower confidence but do not make it unsafe.
Weigh the test evidence above opinions."""


def _case_file(context: PatchContext, evidence: dict, attack: dict | None, other_bugs: list[str]) -> str:
    bug = context.bug
    lines = [
        f"Bug: {bug.title}",
        f"File: {context.patch.file}:{bug.line}",
        f"Root cause: {bug.root_cause or bug.description}",
        "",
        "Code before the patch:",
        redact_text(context.patch.before_code or "")[:3000],
        "",
        "Code after the patch:",
        redact_text(context.patch.after_code or "")[:3000],
        "",
        "Test evidence: " + _evidence_sentence(evidence),
    ]
    if attack:
        lines.append(f"Break-It attack results: {attack.get('headline', '')}")
    if other_bugs:
        lines.append("Other bugs in this project, fixed by separate patches: " + "; ".join(other_bugs[:6]))
    return "\n".join(lines)


def _evidence_sentence(evidence: dict) -> str:
    if not evidence.get("has_run"):
        return "no test run yet."
    parts = []
    if evidence.get("bug_tests_passed") is not None:
        parts.append("edge-case tests for this bug " + ("passed" if evidence["bug_tests_passed"] else "failed") + " on the patched code")
    if evidence.get("generated_failed_before"):
        parts.append("the same tests failed on the original code")
    if evidence.get("regression_passed") is not None:
        parts.append("the full suite " + ("passed" if evidence["regression_passed"] else "failed") + " after patching")
    return "; ".join(parts) + "." if parts else "a test run exists but says nothing about this bug."


def _transcript(turns: list[dict]) -> str:
    return "\n".join(f"Round {turn['round']} {turn['role'].title()}: {turn['text']}" for turn in turns)


def _gemini_turn(role: str, case_file: str, turns: list[dict], round_number: int) -> str:
    from app.llm.gemini import ask_gemini

    prompt = (
        f"{_ROLE_BRIEF[role]}\n\n{case_file}\n\nDebate so far:\n{_transcript(turns) or '(nothing yet)'}\n\n"
        f"This is round {round_number} of {ROUNDS}. Reply in at most 60 words, plain text, no headings."
    )
    return _clean(ask_gemini(prompt, timeout=TURN_TIMEOUT_S, prefer_fast=True))


def _gemini_verdict(case_file: str, turns: list[dict]) -> dict:
    from app.llm.gemini import ask_gemini, strip_fences

    raw = ask_gemini(f"{_JUDGE}\n\n{case_file}\n\nDebate:\n{_transcript(turns)}", json_output=True, timeout=TURN_TIMEOUT_S, prefer_fast=True)
    payload = json.loads(strip_fences(raw))
    verdict = "safe" if str(payload.get("verdict", "")).lower().startswith("safe") else "needs_changes"
    try:
        confidence = int(round(float(payload.get("confidence", 60))))
    except (TypeError, ValueError):
        confidence = 60
    return {
        "verdict": verdict,
        "confidence": max(0, min(100, confidence)),
        "reason": str(payload.get("reason") or "")[:600],
    }


def _clean(text: str) -> str:
    text = re.sub(r"^\s*(Fixer|Breaker|Judge)\s*:\s*", "", text.strip(), flags=re.IGNORECASE)
    return text[:700]


# ---------------------------------------------------------------- rule-based fallback


def _added_lines(context: PatchContext) -> list[str]:
    before = set((context.patch.before_code or "").splitlines())
    return [line.strip() for line in (context.patch.after_code or "").splitlines() if line.strip() and line not in before]


def rule_debate(context: PatchContext, evidence: dict, attack: dict | None) -> tuple[list[dict], dict]:
    added = _added_lines(context)
    guard = next((line for line in added if line.startswith(("if ", "raise", "return"))), added[0] if added else "")
    target = find_target(context.new_source, context.bug.symbol, context.bug.line)
    attacks = [case.label for case in rule_cases(target)] if target else ["an empty input", "None", "a huge value"]
    attacks = attacks or ["an empty input"]
    name = target.name if target else (context.bug.symbol or "the function")
    tests_line = _evidence_sentence(evidence)

    fixer = [
        f"The patch targets the root cause directly: {(context.bug.root_cause or context.bug.title).rstrip('.')}. "
        + (f"The new line `{guard}` handles it before the failing operation runs." if guard else "It changes only the failing lines."),
        (
            "The generated edge-case tests for this bug pass on the patched code."
            if evidence.get("bug_tests_passed")
            else "The fix is small and local, so the risk of side effects is low, but it still needs a test run as proof."
        ),
        (
            "The full test suite still passes after the patch, so nothing that worked before was broken."
            if evidence.get("regression_passed")
            else "No regression run has passed yet, so I'd rather prove it with the test runner than argue."
        ),
    ]
    breaker = [
        f"What happens when `{name}` gets {attacks[0]}? That is exactly the kind of input the original code choked on.",
        f"Fine, but try {attacks[1 % len(attacks)]} and {attacks[2 % len(attacks)]}. A guard for one case often misses its neighbours.",
        "Even if the bug is gone, did the change break callers that relied on the old behaviour?",
    ]
    if attack:
        breaker[1] = f"I ran the Break-It attack: {attack.get('headline', '')}. Anything that still breaks is on you."
        fixer[1] = (
            f"The attack scoreboard backs me up: {attack.get('headline', '')}."
            if attack.get("new_survived") == attack.get("total")
            else f"The scoreboard shows {attack.get('total', 0) - attack.get('new_survived', 0)} input(s) still break, so that part needs another look."
        )
    turns = []
    for index in range(ROUNDS):
        turns.append({"round": index + 1, "role": "breaker", "text": breaker[index], "engine": "rules"})
        turns.append({"round": index + 1, "role": "fixer", "text": fixer[index], "engine": "rules"})

    proven = bool(evidence.get("bug_tests_passed") and evidence.get("regression_passed") is not False)
    attack_clean = attack is None or attack.get("new_survived") == attack.get("total")
    confidence = int(round((context.patch.confidence or 0.5) * 100))
    if proven and attack_clean:
        verdict, confidence = "safe", max(confidence, 85)
    elif not evidence.get("has_run") and attack_clean and confidence >= 85:
        verdict, confidence = "safe", min(confidence, 70)
    else:
        verdict, confidence = "needs_changes", min(confidence, 60)
    reason = f"Decided from the evidence, not opinions: {tests_line}" + (
        f" Break-It: {attack['headline']}." if attack else ""
    )
    return turns, {"verdict": verdict, "confidence": confidence, "reason": reason, "engine": "rules"}


# ---------------------------------------------------------------- the debate


def run_debate(
    context: PatchContext,
    evidence: dict,
    attack: dict | None = None,
    use_gemini: bool = True,
    other_bugs: list[str] | None = None,
) -> Iterator[dict]:
    """Yield events: turn, turn, ..., verdict. Falls back to rules if Gemini drops out."""
    from app.llm.gemini import GeminiError, gemini_usable

    fallback_turns, fallback_verdict = rule_debate(context, evidence, attack)
    yield {"type": "start", "rounds": ROUNDS, "bug": context.bug.title, "file": context.patch.file}

    if not (use_gemini and gemini_usable()):
        for turn in fallback_turns:
            yield {"type": "turn", **turn}
        yield {"type": "verdict", **fallback_verdict}
        return

    case_file = _case_file(context, evidence, attack, other_bugs or [])
    turns: list[dict] = []
    try:
        for round_number in range(1, ROUNDS + 1):
            for role in ("breaker", "fixer"):
                text = _gemini_turn(role, case_file, turns, round_number)
                turn = {"round": round_number, "role": role, "text": text, "engine": "gemini"}
                turns.append(turn)
                yield {"type": "turn", **turn}
        verdict = _gemini_verdict(case_file, turns)
        yield {"type": "verdict", **verdict, "engine": "gemini"}
    except (GeminiError, json.JSONDecodeError, ValueError, KeyError) as exc:
        log.info("debate fell back to rules: %s", exc)
        yield {"type": "notice", "text": "Gemini is busy right now, so the rest of the debate is argued from the test results."}
        for turn in fallback_turns[len(turns):]:
            yield {"type": "turn", **turn}
        yield {"type": "verdict", **fallback_verdict}
