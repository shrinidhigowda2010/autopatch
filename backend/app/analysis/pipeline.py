"""Put the two layers together."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.analysis.ast_rules import scan_source
from app.analysis.findings import Finding
from app.analysis.merge import merge_findings
from app.analysis.secrets import scan_secrets
from app.analysis.static_runner import run_static_tools
from app.llm.cache import attach_cache
from app.llm.gemini import GeminiError, analyze_with_gemini

log = logging.getLogger(__name__)

_SKIP_DIRS = {"tests", "__pycache__", ".venv", "venv", "node_modules", ".git", ".tmp"}


@dataclass
class ScanReport:
    findings: list[Finding]
    mode: str
    tool_notes: list[str] = field(default_factory=list)
    gemini_error: str = ""


def python_files(root: Path, include_tests: bool = False) -> list[Path]:
    found = []
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not include_tests and (path.name.startswith("test_") or "tests" in path.parts):
            continue
        found.append(path)
    return sorted(found)


def text_files(root: Path) -> list[Path]:
    suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".env", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".txt", ".md"}
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in suffixes or path.name.startswith(".env"):
            found.append(path)
    return found


def analyze_project(root: Path, sample_id: str | None = None, use_gemini: bool = True) -> ScanReport:
    py_files = python_files(root)
    ast_found: list[Finding] = []
    sources: dict[str, str] = {}
    for path in py_files:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        sources[rel] = text
        ast_found.extend(scan_source(rel, text))
    tool_found, notes = run_static_tools(root, py_files)
    secret_found = scan_secrets(root, text_files(root))
    groups = [ast_found, tool_found, secret_found]
    mode = "live"
    gemini_error = ""
    if use_gemini and sources:
        try:
            groups.append(analyze_with_gemini(list(sources.items())))
            notes.append("gemini finished")
        except GeminiError as exc:
            gemini_error = str(exc)
            notes.append(f"gemini unavailable: {exc}")
            log.info("gemini skipped: %s", exc)
            if sample_id:
                mode = "demo"
        except Exception as exc:  # noqa: BLE001
            gemini_error = str(exc)
            notes.append(f"gemini failed: {exc}")
            if sample_id:
                mode = "demo"
    elif sample_id:
        mode = "demo"
        gemini_error = gemini_error or "GEMINI_API_KEY is not set"
        notes.append("demo mode: Gemini was not called")
    merged = merge_findings(groups)
    if mode == "demo" and sample_id:
        merged = attach_cache(sample_id, merged)
        notes.append("cached model notes attached for this sample")
    merged.sort(key=lambda item: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item.severity, 4), -item.confidence, item.file, item.line))
    return ScanReport(findings=merged, mode=mode, tool_notes=notes, gemini_error=gemini_error)
