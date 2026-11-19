"""Live Repair Race: paste buggy code and time the real pipeline from bug found to verified."""

from __future__ import annotations

import shutil
import tempfile
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.arena.attack import run_attack
from app.arena.context import patch_context
from app.ingest.files import IngestError
from app.ingest.languages import extension_for, guess_language
from app.models import Bug, Patch, User
from app.patching.apply import apply_findings
from app.sandbox.runner import run_pytest
from app.services import create_from_files, finding_from_bug, run_scan, workspace_for
from app.testing.generate import render_tests

_SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_TEST_FILE = "_fixpilot_race_test.py"


def race_filename(code: str, filename: str = "") -> str:
    name = Path(filename.strip()).name if filename.strip() else ""
    return name or "race" + extension_for(guess_language(code))


def run_race(session: Session, code: str, filename: str = "", user_id: str | None = None) -> Iterator[dict]:
    started = time.monotonic()
    user = session.get(User, user_id) if user_id else None

    def stamp() -> float:
        return round(time.monotonic() - started, 2)

    name = race_filename(code, filename)
    project = create_from_files(session, "Repair race", [(name, code)], origin="race", user=user)
    yield {"type": "stage", "stage": "scanning", "t": stamp(), "project_id": project.id}

    scan = run_scan(session, project, user=user)
    bugs = [
        bug
        for bug in session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all()
        if bug.category != "style" and bug.severity != "low"
    ]
    if not bugs:
        yield {"type": "finish", "result": "clean", "t": stamp(), "message": "No real bugs found. Clean code wins this round."}
        return
    patches = {
        patch.bug_id: patch
        for patch in session.scalars(select(Patch).where(Patch.bug_id.in_([bug.id for bug in bugs]))).all()
    }
    bugs.sort(key=lambda bug: (bug.id not in patches, _SEVERITY.get(bug.severity, 4), -bug.confidence))
    bug = bugs[0]
    yield {
        "type": "stage",
        "stage": "bug_found",
        "t": stamp(),
        "count": len(bugs),
        "bug": {"id": bug.id, "title": bug.title, "line": bug.line, "severity": bug.severity, "file": bug.file},
    }

    patch = patches.get(bug.id)
    if patch is None:
        yield {
            "type": "finish",
            "result": "no_fix",
            "t": stamp(),
            "message": "FixPilot found the bug but has no automatic fix for it yet. Open it to see the explanation.",
        }
        return
    yield {"type": "stage", "stage": "fixed", "t": stamp(), "patch_id": patch.id, "diff": patch.diff}

    proof = verify(session, project, bug, patch)
    yield {"type": "stage", "stage": "verified", "t": stamp(), **proof}
    yield {
        "type": "finish",
        "result": "verified" if proof["passed"] else "unverified",
        "t": stamp(),
        "message": proof["summary"],
    }


def verify(session: Session, project, bug: Bug, patch: Patch) -> dict:
    """Generated edge tests before and after the fix; Break-It attacks when no tests exist for the rule."""
    finding = finding_from_bug(bug)
    tests = render_tests([finding])
    if "test_no_actionable_bug" not in tests:
        failed_before, passed_after = _run_tests_both_ways(workspace_for(project), finding, tests)
        return {
            "method": "tests",
            "passed": passed_after,
            "failed_before": failed_before,
            "summary": (
                "Edge-case tests failed on the original code and pass on the fix."
                if failed_before and passed_after
                else "Edge-case tests pass on the fix." if passed_after else "The fix did not pass its edge-case tests."
            ),
        }
    try:
        attack = run_attack(patch_context(session, patch))
    except IngestError as exc:
        return {"method": "none", "passed": False, "failed_before": False, "summary": str(exc)}
    passed = attack["total"] > 0 and attack["new_survived"] == attack["total"]
    return {
        "method": "attack",
        "passed": passed,
        "failed_before": attack["old_crashed"] > 0,
        "summary": attack["headline"],
    }


def _run_tests_both_ways(workspace: Path, finding, tests: str) -> tuple[bool, bool]:
    scratch = Path(tempfile.mkdtemp(prefix="fixpilot-race-"))
    try:
        before, after = scratch / "before", scratch / "after"
        shutil.copytree(workspace, before)
        shutil.copytree(workspace, after)
        apply_findings(after, [finding])
        for folder in (before, after):
            (folder / _TEST_FILE).write_text(tests, encoding="utf-8")
        with ThreadPoolExecutor(max_workers=2) as pool:
            old_job = pool.submit(run_pytest, before, _TEST_FILE)
            new_job = pool.submit(run_pytest, after, _TEST_FILE)
            old, new = old_job.result(), new_job.result()
        return not old.ok, new.ok
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
