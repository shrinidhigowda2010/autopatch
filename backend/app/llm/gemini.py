"""Gemini client with a timeout, retries, and a second model as fallback.

The key is read from GEMINI_API_KEY. When it is missing or the call fails,
callers catch GeminiError and carry on with static analysis.
"""

from __future__ import annotations

import base64
import json
import logging
import time

import httpx

from app.agent.redaction import redact_text
from app.analysis.catalog import needs_review
from app.analysis.findings import Finding, snippet_around
from app.config import settings

log = logging.getLogger(__name__)

_PROMPT = """You are a careful code reviewer looking for real bugs.
Report only defects you can point at in the source: logic errors, missed edge
cases, wrong outputs, and crashes. Do not report style, naming, or missing
docstrings. If you are unsure, leave it out.

Return JSON: {"findings": [{"file": "", "line": 1, "symbol": "", "title": "",
"category": "logic|crash|security|input_validation", "severity": "critical|high|medium|low",
"confidence": 0.0, "impact": "", "root_cause": "", "trigger": "",
"student_explanation": "", "description": ""}]}

Write root_cause as the situation that triggers the bug and why the code does
the wrong thing. student_explanation is the same idea in simpler words.
confidence is your calibrated probability that this is a real bug, from 0 to 1.
"""


_VISION_PROMPT = """This image shows source code: a screenshot, a photo of a screen, or a scan.
Transcribe the code exactly as written, keeping indentation and line breaks.
Do not fix bugs, do not add comments, and do not add explanations.
Leave out line numbers, editor chrome and anything that is not code.

Return JSON: {"filename": "main.py", "code": "..."}.
Pick a sensible filename with the right extension for the language.
If there is no code in the image, return {"filename": "", "code": ""}.
"""


class GeminiError(RuntimeError):
    pass


# A model that just failed (overloaded, rate limited, timed out) sits out for a while,
# so every later call doesn't pay for the same slow failure before reaching the fallback.
COOLDOWN_S = 300.0
TIMEOUT_COOLDOWN_S = 60.0
_cooling_until: dict[str, float] = {}

# A rejected key (401/403) will not start working by retrying, so skip Gemini for a while.
KEY_REJECTED_S = 600.0
_key_rejected_until = 0.0


_last_key_error = ""


def mark_key_rejected(detail: str = "") -> None:
    global _key_rejected_until, _last_key_error
    _key_rejected_until = time.monotonic() + KEY_REJECTED_S
    if detail:
        # Google's own reason (e.g. "API key not valid"), never the key itself.
        _last_key_error = detail.replace(settings.gemini_api_key, "***")[:200] if settings.gemini_api_key else detail[:200]


def last_key_error() -> str:
    return _last_key_error


def google_error_text(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
        return f"{response.status_code} {error.get('status', '')}: {error.get('message', '')}".strip()
    except (ValueError, AttributeError):
        return f"{response.status_code}"


def gemini_usable() -> bool:
    """A key is set and Google has not recently refused it."""
    return settings.gemini_configured and time.monotonic() >= _key_rejected_until


def engine_status() -> str:
    """What the AI layer can do right now: online, busy, key_rejected or off."""
    if not settings.gemini_configured:
        return "off"
    now = time.monotonic()
    if now < _key_rejected_until:
        return "key_rejected"
    models = {settings.gemini_model, settings.gemini_fallback_model}
    if all(now < _cooling_until.get(model, 0.0) for model in models):
        return "busy"
    return "online"


def chat_models() -> list[str]:
    """At most two models for chat: the faster one first, unless it is cooling down."""
    fast, primary = settings.gemini_fallback_model, settings.gemini_model
    order = [fast] if fast == primary else [fast, primary]
    # When every model is cooling down, return nothing so the caller answers from the scan right away.
    return [model for model in order if time.monotonic() >= _cooling_until.get(model, 0.0)]


def model_plan(prefer_fast: bool = False) -> list[tuple[str, int]]:
    """Models to try in order, each with how many attempts it gets.

    prefer_fast puts the lighter fallback model first, for short turn-by-turn calls
    where waiting matters more than depth (debate turns, attack inputs).
    """
    primary, fallback = settings.gemini_model, settings.gemini_fallback_model
    retries = max(1, settings.gemini_retries)
    if primary == fallback:
        return [(primary, retries)]
    if prefer_fast or time.monotonic() < _cooling_until.get(primary, 0.0):
        return [(fallback, retries), (primary, 1)]
    return [(primary, 1), (fallback, retries)]


def mark_failed(model: str, seconds: float = COOLDOWN_S) -> None:
    _cooling_until[model] = time.monotonic() + seconds


def ask_gemini(
    prompt: str | list[dict],
    json_output: bool = False,
    timeout: float | None = None,
    prefer_fast: bool = False,
) -> str:
    """One prompt, primary model first, then the fallback model. A short timeout suits chatty calls."""
    if not gemini_usable():
        raise GeminiError("Gemini is not available")
    errors = []
    for model, attempts in model_plan(prefer_fast):
        try:
            return _generate(model, prompt, json_output=json_output, attempts=attempts, timeout=timeout)
        except GeminiError as exc:
            log.warning("gemini model %s failed: %s", model, exc)
            # Timeouts are usually a passing spike, so sit out briefly; other failures sit out longer.
            mark_failed(model, TIMEOUT_COOLDOWN_S if "timed out" in str(exc) else COOLDOWN_S)
            errors.append(str(exc))
    raise GeminiError("; ".join(errors) or "no model answered")


def analyze_with_gemini(files: list[tuple[str, str]]) -> list[Finding]:
    if not settings.gemini_configured:
        raise GeminiError("GEMINI_API_KEY is not set")
    prompt = _PROMPT + "\n\n" + _bundle(files)
    return _parse(ask_gemini(prompt), files)


def read_code_from_image(data: bytes, mime: str) -> dict:
    """Ask Gemini vision to transcribe the code in an image. Returns {filename, code}."""
    if not settings.gemini_configured:
        raise GeminiError("GEMINI_API_KEY is not set")
    parts: list[dict] = [
        {"text": _VISION_PROMPT},
        {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}},
    ]
    raw = ask_gemini(parts, json_output=True)
    try:
        payload = json.loads(strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini did not return JSON for the image: {exc}") from exc
    if not isinstance(payload, dict):
        raise GeminiError("Gemini returned an unexpected shape for the image")
    return {"filename": str(payload.get("filename") or ""), "code": str(payload.get("code") or "")}


def translate_text(text: str, language: str) -> str:
    if not settings.gemini_configured:
        raise GeminiError("GEMINI_API_KEY is not set")
    name = "Kannada" if language == "kn" else "Hindi"
    prompt = f"Translate the following explanation into {name}. Return only the translation.\n\n{text}"
    return ask_gemini(prompt).strip()


def _bundle(files: list[tuple[str, str]]) -> str:
    parts = []
    for path, source in files[:8]:
        # Secrets never leave the machine; the model sees placeholders instead.
        clipped = redact_text(source[:12000])
        parts.append(f"----- {path} -----\n{clipped}")
    return "\n\n".join(parts)


def _generate(
    model: str,
    prompt: str | list[dict],
    json_output: bool = False,
    attempts: int | None = None,
    timeout: float | None = None,
) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts = [{"text": prompt}] if isinstance(prompt, str) else prompt
    config: dict = {"temperature": 0.1}
    if json_output:
        config["responseMimeType"] = "application/json"
    body = {"contents": [{"parts": parts}], "generationConfig": config}
    last_error = "no response"
    attempts = max(1, attempts or settings.gemini_retries)
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=timeout or settings.gemini_timeout_s) as client:
                response = client.post(url, params={"key": settings.gemini_api_key}, json=body)
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = f"{model} returned {response.status_code}"
                time.sleep(0.6 * (attempt + 1))
                continue
            if response.status_code in {401, 403}:
                mark_key_rejected(google_error_text(response))
            if response.status_code >= 400:
                raise GeminiError(f"{model} returned {response.status_code}")
            payload = response.json()
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except GeminiError:
            raise
        except httpx.TimeoutException as exc:
            # A slow model stays slow; retrying would only double the wait before the fallback.
            raise GeminiError(f"{model} timed out") from exc
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            time.sleep(0.4 * (attempt + 1))
    raise GeminiError(last_error)


def strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text


def _parse(raw: str, files: list[tuple[str, str]]) -> list[Finding]:
    text = strip_fences(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini did not return JSON: {exc}") from exc
    known = {path: source for path, source in files}
    found: list[Finding] = []
    for item in payload.get("findings", []):
        path = str(item.get("file") or "")
        if path not in known:
            continue
        try:
            confidence = float(item.get("confidence", 0.6))
        except (TypeError, ValueError):
            confidence = 0.6
        confidence = max(0.0, min(1.0, confidence))
        line = int(item.get("line") or 1)
        severity = str(item.get("severity") or "medium")
        if severity not in {"critical", "high", "medium", "low"}:
            severity = "medium"
        rule_id = "gemini_" + _slug(str(item.get("title") or "finding"))
        found.append(
            Finding(
                rule_id=rule_id,
                file=path,
                line=line,
                end_line=line,
                symbol=str(item.get("symbol") or ""),
                title=str(item.get("title") or "Possible logic bug")[:300],
                description=str(item.get("description") or item.get("root_cause") or ""),
                category=str(item.get("category") or "logic"),
                severity=severity,
                confidence=confidence,
                impact=str(item.get("impact") or ""),
                root_cause=str(item.get("root_cause") or ""),
                trigger=str(item.get("trigger") or ""),
                student_explanation=str(item.get("student_explanation") or ""),
                explanation_kn="",
                explanation_hi="",
                source="gemini",
                needs_human_review=needs_review(confidence, rule_id),
                snippet=snippet_around(known[path], line),
            )
        )
    return found


def _slug(title: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in title)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")[:40] or "finding"
