"""Secret scan for any text file, including JavaScript when it is uploaded.

Python assignments are also caught by the syntax-tree rule. This pass
exists so a secret hiding in a config, a notebook or a .js file is not missed,
and so the two reports can be merged.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.analysis.catalog import needs_review, text_for
from app.analysis.findings import Finding, snippet_around

_ASSIGN = re.compile(
    r"""(?mx)^(?P<indent>\s*)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*['"](?P<value>[^'"]{8,})['"]"""
)
_NAME = re.compile(r"(password|passwd|secret|api[_-]?key|access[_-]?key|private[_-]?key|token)", re.I)
_AWS = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_PRIVATE = re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")
_SKIP = {"changeme", "password", "secret", "todo", "xxx", "example", "your_password", "redacted"}


def scan_secrets(root: Path, files: list[Path]) -> list[Finding]:
    found: list[Finding] = []
    spec = text_for("hardcoded_secret")
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relpath = path.relative_to(root).as_posix()
        for match in _ASSIGN.finditer(text):
            name = match.group("name")
            value = match.group("value").strip()
            if not _NAME.search(name) or value.lower() in _SKIP:
                continue
            line = text[: match.start()].count("\n") + 1
            found.append(_finding(relpath, line, name, text, spec))
        for pattern in (_AWS, _PRIVATE):
            for match in pattern.finditer(text):
                line = text[: match.start()].count("\n") + 1
                found.append(_finding(relpath, line, "aws_key" if pattern is _AWS else "private_key", text, spec))
    return found


def _finding(relpath: str, line: int, symbol: str, source: str, spec: dict) -> Finding:
    confidence = float(spec["confidence"])
    return Finding(
        rule_id="hardcoded_secret",
        file=relpath,
        line=line,
        end_line=line,
        symbol=symbol,
        title=spec["title"],
        description=spec["description"],
        category=spec["category"],
        severity=spec["severity"],
        confidence=confidence,
        impact=spec["impact"],
        root_cause=spec["root_cause"],
        trigger=spec["trigger"],
        student_explanation=spec["student"],
        explanation_kn=spec["kn"],
        explanation_hi=spec["hi"],
        source="secrets",
        needs_human_review=needs_review(confidence, "hardcoded_secret"),
        snippet=snippet_around(source, line),
        extra={"var": symbol},
    )
