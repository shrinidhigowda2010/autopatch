"""Redact secrets before any project text is sent to an AI model."""

from __future__ import annotations

import re

from app.analysis.secrets import _ASSIGN, _AWS, _NAME, _PRIVATE, _SKIP

_GENERIC_SECRET = re.compile(
    r"""(?ix)\b(?:password|passwd|secret|api[_-]?key|token|private[_-]?key)\b\s*[:=]\s*['"]?([^\s'"]{8,})['"]?"""
)


def redact_text(text: str) -> str:
    if not text:
        return text
    out = text
    for match in list(_ASSIGN.finditer(out)):
        name = match.group("name")
        value = match.group("value").strip()
        if _NAME.search(name) and value.lower() not in _SKIP:
            out = out.replace(match.group(0), f"{match.group('indent')}{name} = '***REDACTED***'")
    out = _AWS.sub("AKIA****************", out)
    out = _PRIVATE.sub("-----BEGIN PRIVATE KEY-----***REDACTED***", out)
    out = _GENERIC_SECRET.sub(lambda m: m.group(0).replace(m.group(1), "***REDACTED***"), out)
    return out


def redact_path_name(path: str) -> bool:
    """Return True if this path should never be sent to the model."""
    lowered = path.lower().replace("\\", "/")
    name = lowered.rsplit("/", 1)[-1]
    if name in {".env", ".env.local", ".env.production", "credentials.json", "secrets.yaml", "secrets.yml"}:
        return True
    if name.endswith(".pem") or name.endswith(".key"):
        return True
    return False
