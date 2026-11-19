"""Apply every fixer that matches. Used by the test step and by 'apply safe fixes'."""

from __future__ import annotations

from pathlib import Path

from app.analysis.findings import Finding
from app.patching.fixers import propose_fix


def apply_findings(root: Path, findings: list[Finding]) -> list[str]:
    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(finding.file, []).append(finding)
    changed: list[str] = []
    for relpath, group in grouped.items():
        path = root / relpath
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        original = source
        for finding in group:
            updated = propose_fix(source, finding.rule_id, finding.symbol, finding.extra)
            if updated and updated != source:
                source = updated
        if source != original:
            path.write_text(source, encoding="utf-8")
            changed.append(relpath)
    return changed
