"""Put the two layers together."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from app.analysis.ast_rules import scan_source
from app.analysis.findings import Finding
from app.analysis.merge import merge_findings
from app.analysis.secrets import scan_secrets
from app.analysis.static_runner import run_static_tools
from app.ingest.languages import CODE_LANGUAGES, LANGUAGES
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
    suffixes = set(LANGUAGES)
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in suffixes or path.name.startswith(".env"):
            found.append(path)
    return found


def other_code_files(root: Path) -> list[Path]:
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        suffix = path.suffix.lower()
        if suffix in CODE_LANGUAGES and suffix != ".py":
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
    other_code = other_code_files(root)
    for path in other_code:
        sources[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8", errors="replace")

    # Gemini is the slow part, so it runs while the static tools do their work.
    pool = ThreadPoolExecutor(max_workers=1)
    ai_job = pool.submit(analyze_with_gemini, list(sources.items())) if use_gemini and sources else None
    try:
        tool_found, notes = run_static_tools(root, py_files)
        if other_code:
            # Static tools and sandbox tests cover Python only; other languages get AI analysis.
            notes.append(f"{len(other_code)} non-Python file(s): AI analysis only, not verified by tests")
        secret_found = scan_secrets(root, text_files(root))
        groups = [ast_found, tool_found, secret_found]
        mode = "live"
        gemini_error = ""
        if ai_job is not None:
            try:
                groups.append(ai_job.result())
                notes.append("gemini finished")
            except GeminiError as exc:
                gemini_error = str(exc)
                notes.append("Gemini unavailable right now, static analysis did the scan")
                log.info("gemini skipped: %s", exc)
                if sample_id:
                    mode = "demo"
            except Exception as exc:  # noqa: BLE001
                gemini_error = str(exc)
                notes.append("Gemini unavailable right now, static analysis did the scan")
                if sample_id:
                    mode = "demo"
    finally:
        pool.shutdown(wait=False)
    if ai_job is None and sample_id:
        mode = "demo"
        gemini_error = gemini_error or "GEMINI_API_KEY is not set"
        notes.append("Gemini unavailable right now, static analysis did the scan")
    merged = merge_findings(groups)
    if mode == "demo" and sample_id:
        merged = attach_cache(sample_id, merged)
        notes.append("added notes from the project's known-bug list")
    merged.sort(key=lambda item: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item.severity, 4), -item.confidence, item.file, item.line))
    return ScanReport(findings=merged, mode=mode, tool_notes=notes, gemini_error=gemini_error)
