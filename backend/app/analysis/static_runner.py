"""Run pylint, pyflakes and bandit, and turn their reports into findings."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from app.analysis.catalog import needs_review, text_for
from app.analysis.findings import Finding, snippet_around

log = logging.getLogger(__name__)

_DEF = re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)")
_ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def run_static_tools(root: Path, files: list[Path]) -> tuple[list[Finding], list[str]]:
    notes: list[str] = []
    if not files:
        return [], ["No Python files to lint."]
    found: list[Finding] = []
    for name, func in (("pylint", _pylint), ("pyflakes", _pyflakes), ("bandit", _bandit)):
        try:
            found.extend(func(root, files))
            notes.append(f"{name} finished")
        except Exception as exc:  # noqa: BLE001
            log.warning("%s failed: %s", name, exc)
            notes.append(f"{name} failed: {exc}")
    return found, notes


def _run(argv: list[str], cwd: Path, timeout: int = 40) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _rel(root: Path, raw: str) -> str:
    path = Path(raw)
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _symbol(source: str, line: int, prefer_function: bool) -> str:
    rows = source.splitlines()
    if not prefer_function and 1 <= line <= len(rows):
        match = _ASSIGN.match(rows[line - 1])
        if match and match.group(1) not in {"if", "for", "while", "return", "with"}:
            return match.group(1)
    for index in range(min(line, len(rows)) - 1, -1, -1):
        match = _DEF.match(rows[index])
        if match:
            return match.group(1)
    return ""


def _read(root: Path, relpath: str) -> str:
    path = root / relpath
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def _base(rule_id: str, relpath: str, line: int, symbol: str, source: str, tool: str, **overrides: object) -> Finding:
    spec = dict(text_for(rule_id))
    spec.update(overrides)
    confidence = float(spec["confidence"])
    return Finding(
        rule_id=rule_id,
        file=relpath,
        line=line,
        end_line=int(spec.get("end_line", line)),
        symbol=symbol,
        title=str(spec["title"]),
        description=str(spec["description"]),
        category=str(spec["category"]),
        severity=str(spec["severity"]),
        confidence=confidence,
        impact=str(spec["impact"]),
        root_cause=str(spec["root_cause"]),
        trigger=str(spec["trigger"]),
        student_explanation=str(spec["student"]),
        explanation_kn=str(spec["kn"]),
        explanation_hi=str(spec["hi"]),
        source=tool,
        needs_human_review=needs_review(confidence, rule_id),
        snippet=snippet_around(source, line) if source else "",
    )


def _pylint(root: Path, files: list[Path]) -> list[Finding]:
    proc = _run(
        [sys.executable, "-m", "pylint", "--output-format=json", "--score=n", "--disable=import-error", *[str(p) for p in files]],
        root,
    )
    raw = proc.stdout.strip()
    if not raw:
        return []
    try:
        messages = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(messages, dict):
        messages = [messages]
    found = []
    for message in messages:
        relpath = _rel(root, message.get("path", ""))
        line = int(message.get("line") or 1)
        code = message.get("message-id", "W0000")
        source = _read(root, relpath)
        kind = message.get("type", "warning")
        if code == "W0102":
            symbol = message.get("obj") or _symbol(source, line, prefer_function=True)
            found.append(_base("mutable_default_argument", relpath, line, symbol, source, "pylint"))
            continue
        if kind in {"convention", "refactor", "info"}:
            severity, category, confidence = "low", "style", 0.4
        elif kind in {"error", "fatal"}:
            severity, category, confidence = "high", "crash", 0.7
        else:
            severity, category, confidence = "low", "style", 0.45
        symbol = message.get("obj") or ""
        text = message.get("message", code)
        found.append(
            _base(
                f"pylint_{code}",
                relpath,
                line,
                symbol,
                source,
                "pylint",
                title=text[:180],
                description=text,
                category=category,
                severity=severity,
                confidence=confidence,
                impact="A style or quality note from pylint. It may not change what the program does.",
                root_cause=text,
                trigger=f"pylint reported {code} on line {line}.",
                student="A style checker marked this line. It is not necessarily a bug in the result.",
                kn="ಶೈಲಿ ಪರೀಕ್ಷಕ ಈ ಸಾಲನ್ನು ಗುರುತಿಸಿದೆ. ಇದು ಫಲಿತಾಂಶದ ದೋಷವೇ ಎಂದು ಹೇಳಲಾಗದು.",
                hi="एक शैली जाँच ने इस पंक्ति को चिह्नित किया। यह ज़रूरी नहीं कि परिणाम की गलती हो।",
            )
        )
    return found


def _pyflakes(root: Path, files: list[Path]) -> list[Finding]:
    proc = _run([sys.executable, "-m", "pyflakes", *[str(p) for p in files]], root)
    found = []
    pattern = re.compile(r"^(.*?):(\d+):\d+:\s*(.*)$")
    for line in proc.stdout.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        relpath = _rel(root, match.group(1))
        number = int(match.group(2))
        text = match.group(3)
        source = _read(root, relpath)
        undefined = text.lower().startswith("undefined name")
        found.append(
            _base(
                "undefined_name" if undefined else "pyflakes",
                relpath,
                number,
                _symbol(source, number, prefer_function=True),
                source,
                "pyflakes",
                title=text[:180],
                description=text,
                category="crash" if undefined else "style",
                severity="high" if undefined else "low",
                confidence=0.8 if undefined else 0.4,
                impact="The name is not defined, so the line crashes when it runs." if undefined else "pyflakes noticed an unused or odd name.",
                root_cause=text,
                trigger="Import or run the module and reach this line." if undefined else "Open the line pyflakes marked.",
                student="The program uses a name it never created." if undefined else "A checker thinks this name is unused.",
                kn="ಪ್ರೋಗ್ರಾಂ ರಚಿಸದ ಹೆಸರನ್ನು ಬಳಸುತ್ತದೆ." if undefined else "ಪರೀಕ್ಷಕ ಈ ಹೆಸರು ಬಳಕೆಯಾಗಿಲ್ಲ ಎಂದು ಭಾವಿಸುತ್ತದೆ.",
                hi="प्रोग्राम एक ऐसे नाम का उपयोग करता है जिसे बनाया नहीं गया।" if undefined else "जाँचक को यह नाम बिना उपयोग का लगता है।",
            )
        )
    return found


def _bandit(root: Path, files: list[Path]) -> list[Finding]:
    proc = _run([sys.executable, "-m", "bandit", "-f", "json", "-q", *[str(p) for p in files]], root)
    raw = proc.stdout.strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    found = []
    for item in payload.get("results", []):
        relpath = _rel(root, item.get("filename", ""))
        line = int(item.get("line_number") or 1)
        test_id = item.get("test_id", "B000")
        source = _read(root, relpath)
        severity = (item.get("issue_severity") or "LOW").upper()
        text = item.get("issue_text") or test_id
        if test_id == "B608":
            found.append(_base("sql_injection", relpath, line, _symbol(source, line, True), source, "bandit"))
            continue
        if test_id in {"B105", "B106", "B107"}:
            found.append(
                _base("hardcoded_secret", relpath, line, _symbol(source, line, False), source, "bandit")
            )
            continue
        if test_id == "B101" or severity == "LOW":
            level, category, confidence = "low", "style", 0.35
        elif severity == "HIGH":
            level, category, confidence = "critical", "security", 0.85
        else:
            level, category, confidence = "high", "security", 0.75
        found.append(
            _base(
                f"bandit_{test_id}",
                relpath,
                line,
                _symbol(source, line, True),
                source,
                "bandit",
                title=f"{test_id}: {text[:160]}",
                description=text,
                category=category,
                severity=level,
                confidence=confidence,
                impact=text,
                root_cause=text,
                trigger=f"bandit rule {test_id} matched line {line}.",
                student="A security checker marked this line.",
                kn="ಭದ್ರತಾ ಪರೀಕ್ಷಕ ಈ ಸಾಲನ್ನು ಗುರುತಿಸಿದೆ.",
                hi="एक सुरक्षा जाँच ने इस पंक्ति को चिह्नित किया।",
            )
        )
    return found
