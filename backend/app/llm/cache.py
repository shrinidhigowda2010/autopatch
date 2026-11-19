"""Cached model notes for the bundled samples.

Used only when Gemini is not configured or the request fails, and only for
projects that were loaded from samples/. Live static findings stay live.
"""

from __future__ import annotations

import json
import logging

from app.analysis.findings import Finding
from app.config import settings

log = logging.getLogger(__name__)


def attach_cache(sample_id: str, findings: list[Finding]) -> list[Finding]:
    cached = _load(sample_id)
    if not cached:
        for finding in findings:
            finding.demo_cache_used = True
        return findings
    index = {(item.get("file"), item.get("rule_id"), item.get("symbol")): item for item in cached}
    seen = set()
    for finding in findings:
        key = (finding.file, finding.rule_id, finding.symbol)
        note = index.get(key)
        if not note:
            continue
        seen.add(key)
        finding.demo_cache_used = True
        if note.get("root_cause"):
            finding.extra["cached_root_cause"] = note["root_cause"]
        if note.get("student_explanation"):
            finding.extra["cached_student"] = note["student_explanation"]
    return findings


def _load(sample_id: str) -> list[dict]:
    path = settings.samples_dir / "cache.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("sample cache is not valid JSON")
        return []
    block = payload.get(sample_id) or {}
    return list(block.get("findings") or [])
