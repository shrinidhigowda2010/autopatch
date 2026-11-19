"""Measure detection, false positives and fix success on the bundled samples.

Numbers come from running the analysers and the oracles. Nothing here is typed in by hand.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.analysis.pipeline import analyze_project
from app.config import settings
from app.patching.fixers import propose_fix

_ACTIONABLE = {"critical", "high", "medium"}


def sample_catalog() -> list[dict]:
    rows = []
    for path in sorted(settings.samples_dir.iterdir()):
        truth_path = path / "ground_truth.json"
        if not truth_path.is_file():
            continue
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        rows.append(
            {
                "id": truth["id"],
                "title": truth["title"],
                "blurb": truth["blurb"],
                "bugs": len(truth["bugs"]),
            }
        )
    return rows


def run_benchmark() -> dict:
    projects = []
    totals = {"truth": 0, "detected": 0, "false_positives": 0, "actionable": 0, "fixed_bugs": 0, "projects_fixed": 0}
    for sample in sorted(settings.samples_dir.iterdir()):
        if not (sample / "ground_truth.json").is_file():
            continue
        projects.append(_one(sample, totals))
    truth = totals["truth"] or 1
    detected = totals["detected"]
    actionable = totals["actionable"] or 1
    return {
        "projects": projects,
        "detection_rate": round(detected / truth, 4),
        "false_positive_count": totals["false_positives"],
        "false_positive_rate": round(totals["false_positives"] / actionable, 4),
        "fix_success_rate": round(totals["fixed_bugs"] / truth, 4),
        "projects_fixed": totals["projects_fixed"],
        "project_count": len(projects),
        "bug_count": totals["truth"],
        "method": (
            "Each sample is scanned with the AST rules, pylint, pyflakes, bandit and the secret scanner. "
            "Gemini is not called, so the numbers do not depend on an API key. "
            "A finding matches ground truth when the file, rule and symbol agree. "
            "Style notes and low-severity linter messages are shown in the app but are not counted as false-positive bugs. "
            "A bug counts as fixed when applying the generated patches makes that sample's oracle pass and its existing tests still pass."
        ),
    }


def _one(sample: Path, totals: dict) -> dict:
    truth = json.loads((sample / "ground_truth.json").read_text(encoding="utf-8"))
    report = analyze_project(sample / "project", sample_id=None, use_gemini=False)
    actionable = [
        finding
        for finding in report.findings
        if finding.severity in _ACTIONABLE and finding.category != "style"
    ]
    matched = []
    used = set()
    missed = []
    for bug in truth["bugs"]:
        hit = None
        for index, finding in enumerate(actionable):
            if index in used:
                continue
            if finding.file == bug["file"] and finding.rule_id == bug["rule_id"] and finding.symbol == bug["symbol"]:
                hit = index
                break
        if hit is None:
            missed.append(bug["rule_id"] + ":" + bug["symbol"])
        else:
            used.add(hit)
            matched.append(actionable[hit])
    false_positives = [
        {"rule_id": finding.rule_id, "file": finding.file, "symbol": finding.symbol, "severity": finding.severity}
        for index, finding in enumerate(actionable)
        if index not in used
    ]
    fixed = _fixes_pass(sample, matched)
    totals["truth"] += len(truth["bugs"])
    totals["detected"] += len(matched)
    totals["false_positives"] += len(false_positives)
    totals["actionable"] += len(actionable)
    if fixed:
        totals["fixed_bugs"] += len(matched)
        totals["projects_fixed"] += 1
    return {
        "id": truth["id"],
        "title": truth["title"],
        "ground_truth": len(truth["bugs"]),
        "detected": len(matched),
        "missed": missed,
        "false_positives": false_positives,
        "fixed": fixed,
    }


def _fixes_pass(sample: Path, findings: list) -> bool:
    if not findings:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "project"
        shutil.copytree(sample / "project", work)
        for finding in findings:
            path = work / finding.file
            source = path.read_text(encoding="utf-8")
            updated = propose_fix(source, finding.rule_id, finding.symbol, finding.extra)
            if not updated:
                return False
            path.write_text(updated, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(f"oracle_{sample.name}", sample / "oracle.py")
        oracle = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(oracle)
        if oracle.check(work):
            return False
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        return proc.returncode == 0
