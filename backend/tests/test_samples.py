"""Detection and repair of the eight bundled projects, measured against their oracles."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.analysis.ast_rules import scan_source
from app.config import settings
from app.patching.fixers import propose_fix

SAMPLES = settings.samples_dir


def _project_py(project: Path) -> list[Path]:
    files = []
    for path in project.rglob("*.py"):
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        files.append(path)
    return files


def _scan(project: Path):
    found = []
    for path in _project_py(project):
        rel = path.relative_to(project).as_posix()
        found.extend(scan_source(rel, path.read_text(encoding="utf-8")))
    return found


def _match(found, truths):
    used = set()
    pairs = []
    for truth in truths:
        hit = None
        for index, finding in enumerate(found):
            if index in used:
                continue
            if finding.file == truth["file"] and finding.rule_id == truth["rule_id"] and finding.symbol == truth["symbol"]:
                hit = index
                break
        if hit is not None:
            used.add(hit)
            pairs.append(found[hit])
    missed = [truth for truth in truths if not any(
        f.file == truth["file"] and f.rule_id == truth["rule_id"] and f.symbol == truth["symbol"] for f in pairs
    )]
    return pairs, missed


def test_every_sample_is_detected_and_fixed(tmp_path: Path):
    sample_dirs = sorted(path for path in SAMPLES.iterdir() if (path / "ground_truth.json").is_file())
    assert len(sample_dirs) >= 7
    for sample in sample_dirs:
        truth = json.loads((sample / "ground_truth.json").read_text(encoding="utf-8"))
        project = sample / "project"
        found = _scan(project)
        matched, missed = _match(found, truth["bugs"])
        assert not missed, f"{sample.name} missed {missed}; saw {[(f.rule_id, f.symbol, f.line) for f in found]}"

        work = tmp_path / sample.name
        shutil.copytree(project, work)
        for bug in truth["bugs"]:
            path = work / bug["file"]
            source = path.read_text(encoding="utf-8")
            finding = next(
                item for item in matched if item.rule_id == bug["rule_id"] and item.symbol == bug["symbol"]
            )
            updated = propose_fix(source, finding.rule_id, finding.symbol, finding.extra)
            assert updated, f"{sample.name} produced no patch for {bug['rule_id']}"
            path.write_text(updated, encoding="utf-8")

        spec = importlib.util.spec_from_file_location(f"oracle_{sample.name}", sample / "oracle.py")
        oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)
        failures = oracle.check(work)
        assert failures == [], f"{sample.name} oracle: {failures}"

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=40,
        )
        assert proc.returncode == 0, f"{sample.name} regression\n{proc.stdout}\n{proc.stderr}"
