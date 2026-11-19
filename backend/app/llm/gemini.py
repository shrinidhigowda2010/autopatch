"""Gemini client with a timeout, retries, and a second model as fallback.

The key is read from GEMINI_API_KEY. When it is missing or the call fails,
callers catch GeminiError and switch the scan to demo mode.
"""

from __future__ import annotations

import base64
import json
import logging
import time

import httpx

from app.analysis.catalog import needs_review
from app.agent.redaction import redact_text
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


def analyze_with_gemini(files: list[tuple[str, str]]) -> list[Finding]:
    if not settings.gemini_configured:
        raise GeminiError("GEMINI_API_KEY is not set")
    prompt = _PROMPT + "\n\n" + _bundle(files)
    try:
        raw = _generate(settings.gemini_model, prompt)
    except GeminiError as first:
        log.warning("primary gemini model failed: %s", first)
        raw = _generate(settings.gemini_fallback_model, prompt)
    return _parse(raw, files)


def read_code_from_image(data: bytes, mime: str) -> dict:
    """Ask Gemini vision to transcribe the code in an image. Returns {filename, code}."""
    if not settings.gemini_configured:
        raise GeminiError("GEMINI_API_KEY is not set")
    parts = [
        {"text": _VISION_PROMPT},
        {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}},
    ]
    try:
        raw = _generate(settings.gemini_model, parts, json_output=True)
    except GeminiError as first:
        log.warning("primary gemini model failed on an image: %s", first)
        raw = _generate(settings.gemini_fallback_model, parts, json_output=True)
    try:
        payload = json.loads(_strip_fences(raw))
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
    return _generate(settings.gemini_model, prompt).strip()


def _bundle(files: list[tuple[str, str]]) -> str:
    parts = []
    for path, source in files[:8]:
        # Secrets never leave the machine; the model sees placeholders instead.
        clipped = redact_text(source[:12000])
        parts.append(f"----- {path} -----\n{clipped}")
    return "\n\n".join(parts)


def _generate(model: str, prompt: str | list[dict], json_output: bool = False) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts = [{"text": prompt}] if isinstance(prompt, str) else prompt
    config: dict = {"temperature": 0.1}
    if json_output:
        config["responseMimeType"] = "application/json"
    body = {"contents": [{"parts": parts}], "generationConfig": config}
    last_error = "no response"
    attempts = max(1, settings.gemini_retries)
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=settings.gemini_timeout_s) as client:
                response = client.post(url, params={"key": settings.gemini_api_key}, json=body)
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = f"{model} returned {response.status_code}"
                time.sleep(0.6 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise GeminiError(f"{model} returned {response.status_code}")
            payload = response.json()
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except GeminiError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            time.sleep(0.4 * (attempt + 1))
    raise GeminiError(last_error)


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text


def _parse(raw: str, files: list[tuple[str, str]]) -> list[Finding]:
    text = _strip_fences(raw)
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
