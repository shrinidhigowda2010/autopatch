"""Create projects, run scans, record decisions. Routes stay thin."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.pipeline import analyze_project
from app.ids import new_id
from app.ingest.files import IngestError, copy_project, extract_zip, project_paths, save_single_file
from app.ingest.github import download_github
from app.ingest.structure import describe_project
from app.models import Bug, Decision, HistoryEvent, Patch, Project, Scan, TestRun
from app.patching.diffgen import changed_region, unified_diff
from app.patching.fixers import propose_fix
from app.testing.service import prove

log = logging.getLogger(__name__)

_SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def record(session: Session, project_id: str, kind: str, message: str, bug_id: str | None = None) -> None:
    session.add(HistoryEvent(project_id=project_id, bug_id=bug_id, kind=kind, message=message))


def _store_meta(project: Project, workspace: Path) -> None:
    meta = describe_project(workspace)
    project.file_count = meta["file_count"]
    project.languages_json = json.dumps(meta["languages"])
    project.dependencies_json = json.dumps(meta["dependencies"])
    project.important_json = json.dumps(meta["important"])
    project.graph_json = json.dumps(meta["graph"])
    project.tree_json = json.dumps(meta["tree"])


def create_from_sample(session: Session, sample_id: str, title: str, origin: Path) -> Project:
    project = Project(id=new_id(), name=title, source_type="sample", sample_id=sample_id)
    session.add(project)
    session.flush()
    workspace = copy_project(origin, project.id)
    _store_meta(project, workspace)
    record(session, project.id, "upload", f"Loaded sample “{title}”.")
    session.commit()
    return project


def create_from_upload(session: Session, filename: str, data: bytes) -> Project:
    project = Project(
        id=new_id(),
        name=Path(filename).stem or "upload",
        source_type="zip" if filename.lower().endswith(".zip") else "upload",
    )
    session.add(project)
    session.flush()
    if filename.lower().endswith(".zip"):
        workspace = extract_zip(project.id, data)
    else:
        workspace = save_single_file(project.id, filename, data)
    _store_meta(project, workspace)
    record(session, project.id, "upload", f"Uploaded {filename}.")
    session.commit()
    return project


def create_from_github(session: Session, url: str) -> Project:
    origin = download_github(url)
    try:
        project = Project(id=new_id(), name=url.rstrip("/").split("/")[-1], source_type="github", github_url=url)
        session.add(project)
        session.flush()
        workspace = copy_project(origin, project.id)
        _store_meta(project, workspace)
        record(session, project.id, "upload", f"Cloned {url}.")
        session.commit()
        return project
    finally:
        shutil.rmtree(origin.parent, ignore_errors=True)


def workspace_for(project: Project) -> Path:
    _source, workspace = project_paths(project.id)
    return workspace


def run_scan(session: Session, project: Project) -> Scan:
    scan = Scan(id=new_id(), project_id=project.id, status="running")
    session.add(scan)
    session.flush()
    record(session, project.id, "scan_started", "Scan started.")
    session.commit()
    workspace = workspace_for(project)
    try:
        report = analyze_project(workspace, sample_id=project.sample_id, use_gemini=True)
    except Exception as exc:  # noqa: BLE001
        log.exception("scan failed")
        scan.status = "error"
        scan.error = str(exc)
        scan.finished_at = datetime.now(timezone.utc)
        record(session, project.id, "scan_error", f"Scan failed: {exc}")
        session.commit()
        return scan
    scan.mode = report.mode
    scan.tool_notes_json = json.dumps(report.tool_notes)
    scan.error = report.gemini_error
    for finding in report.findings:
        bug = Bug(
            id=new_id(),
            scan_id=scan.id,
            project_id=project.id,
            rule_id=finding.rule_id,
            symbol=finding.symbol,
            file=finding.file,
            line=finding.line,
            end_line=finding.end_line,
            title=finding.title,
            description=finding.description,
            category=finding.category,
            severity=finding.severity,
            confidence=finding.confidence,
            impact=finding.impact,
            needs_human_review=finding.needs_human_review,
            root_cause=finding.root_cause,
            trigger=finding.trigger,
            student_explanation=finding.student_explanation,
            explanation_kn=finding.explanation_kn,
            explanation_hi=finding.explanation_hi,
            source=finding.source,
            snippet=finding.snippet,
            extra_json=json.dumps(finding.extra),
            demo_cache_used=finding.demo_cache_used,
        )
        session.add(bug)
        session.flush()
        _propose_patch(session, project, bug, workspace)
        record(session, project.id, "bug_found", finding.title, bug_id=bug.id)
    scan.status = "complete"
    scan.finished_at = datetime.now(timezone.utc)
    record(
        session,
        project.id,
        "scan_finished",
        f"Scan finished in {report.mode} mode with {len(report.findings)} finding(s).",
    )
    session.commit()
    return scan


def _propose_patch(session: Session, project: Project, bug: Bug, workspace: Path) -> None:
    if bug.category == "style" or bug.severity == "low":
        return
    path = workspace / bug.file
    if not path.is_file():
        return
    source = path.read_text(encoding="utf-8")
    extra = json.loads(bug.extra_json or "{}")
    updated = propose_fix(source, bug.rule_id, bug.symbol, extra)
    if not updated:
        return
    before, after = changed_region(source, updated)
    patch = Patch(
        id=new_id(),
        bug_id=bug.id,
        project_id=project.id,
        file=bug.file,
        diff=unified_diff(bug.file, source, updated),
        before_code=before,
        after_code=after,
        status="proposed",
        source="rule" if "cached_demo" not in bug.source else "cached_demo",
        confidence=bug.confidence,
    )
    session.add(patch)
    record(session, project.id, "patch_proposed", f"Patch proposed for {bug.title}.", bug_id=bug.id)


def decide_patch(session: Session, patch: Patch, action: str, note: str = "") -> Patch:
    if action not in {"accept", "reject"}:
        raise IngestError("Decision must be accept or reject.")
    if patch.status in {"applied", "rejected"}:
        raise IngestError(f"This patch is already {patch.status}.")
    project = session.get(Project, patch.project_id)
    bug = session.get(Bug, patch.bug_id)
    if action == "reject":
        patch.status = "rejected"
        session.add(Decision(id=new_id(), patch_id=patch.id, project_id=patch.project_id, action="reject", note=note))
        record(session, patch.project_id, "rejected", f"Rejected the patch for {bug.title if bug else patch.file}.", bug.id if bug else None)
        session.commit()
        return patch
    if project is None or bug is None:
        raise IngestError("Patch is missing its project.", status=404)
    workspace = workspace_for(project)
    path = workspace / bug.file
    source = path.read_text(encoding="utf-8")
    updated = propose_fix(source, bug.rule_id, bug.symbol, json.loads(bug.extra_json or "{}"))
    if not updated:
        raise IngestError("The patch no longer applies. The file may already be fixed.")
    path.write_text(updated, encoding="utf-8")
    patch.status = "applied"
    patch.diff = unified_diff(bug.file, source, updated)
    before, after = changed_region(source, updated)
    patch.before_code = before
    patch.after_code = after
    session.add(Decision(id=new_id(), patch_id=patch.id, project_id=project.id, action="accept", note=note))
    record(session, project.id, "accepted", f"Accepted and applied the patch for {bug.title}.", bug.id)
    session.commit()
    return patch


def apply_safe(session: Session, project: Project, scan: Scan) -> dict:
    run = session.scalar(
        select(TestRun).where(TestRun.project_id == project.id).order_by(TestRun.created_at.desc())
    )
    if run is None or run.status not in {"passed", "failed"}:
        raise IngestError("Run the tests before applying safe fixes. A patch is safe only after its tests pass.")
    summary = json.loads(run.summary_json or "{}")
    passed_keys = {
        (item.get("file"), item.get("rule_id"), item.get("symbol"))
        for item in summary.get("per_bug", [])
        if item.get("passed")
    }
    if not summary.get("regression_passed"):
        raise IngestError("The regression suite failed, so nothing is marked safe.")
    bugs = session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all()
    applied = []
    skipped = []
    workspace = workspace_for(project)
    for bug in bugs:
        patch = session.scalar(select(Patch).where(Patch.bug_id == bug.id).order_by(Patch.created_at.desc()))
        if patch is None or patch.status != "proposed":
            continue
        key = (bug.file, bug.rule_id, bug.symbol)
        safe = (
            bug.confidence >= 0.8
            and not bug.needs_human_review
            and key in passed_keys
            and "cached_demo" not in (bug.source or "")
        )
        if not safe:
            skipped.append({"bug_id": bug.id, "title": bug.title, "reason": "low confidence, needs review, or its test did not pass"})
            continue
        path = workspace / bug.file
        source = path.read_text(encoding="utf-8")
        updated = propose_fix(source, bug.rule_id, bug.symbol, json.loads(bug.extra_json or "{}"))
        if not updated:
            skipped.append({"bug_id": bug.id, "title": bug.title, "reason": "patch did not apply cleanly"})
            continue
        path.write_text(updated, encoding="utf-8")
        patch.status = "applied"
        session.add(Decision(id=new_id(), patch_id=patch.id, project_id=project.id, action="accept", note="Applied by safe-fix. Tests passed and confidence was high."))
        record(session, project.id, "accepted", f"Safe fix applied: {bug.title}.", bug.id)
        applied.append({"bug_id": bug.id, "title": bug.title, "file": bug.file})
    session.commit()
    return {"applied": applied, "skipped": skipped}


def latest_scan(session: Session, project_id: str) -> Scan | None:
    return session.scalar(select(Scan).where(Scan.project_id == project_id).order_by(Scan.started_at.desc()))


def run_tests_job(run_id: str) -> None:
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        run = session.get(TestRun, run_id)
        if run is None:
            return
        project = session.get(Project, run.project_id)
        scan = latest_scan(session, project.id) if project else None
        bugs = []
        if scan:
            bugs = list(session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all())
        from app.analysis.findings import Finding

        findings = []
        for bug in bugs:
            findings.append(
                Finding(
                    rule_id=bug.rule_id,
                    file=bug.file,
                    line=bug.line,
                    end_line=bug.end_line,
                    symbol=bug.symbol,
                    title=bug.title,
                    description=bug.description,
                    category=bug.category,
                    severity=bug.severity,
                    confidence=bug.confidence,
                    impact=bug.impact,
                    root_cause=bug.root_cause,
                    trigger=bug.trigger,
                    student_explanation=bug.student_explanation,
                    explanation_kn=bug.explanation_kn,
                    explanation_hi=bug.explanation_hi,
                    source=bug.source,
                    needs_human_review=bug.needs_human_review,
                    snippet=bug.snippet,
                    extra=json.loads(bug.extra_json or "{}"),
                    demo_cache_used=bug.demo_cache_used,
                )
            )

        def emit(message: str, status: str = "info", payload: dict | None = None) -> None:
            from app.models import TestEvent

            session.add(
                TestEvent(
                    test_run_id=run_id,
                    message=message,
                    status=status,
                    payload_json=json.dumps(payload or {}),
                )
            )
            session.commit()

        run.status = "running"
        session.commit()
        record(session, project.id, "test_started", "Test run started.")
        session.commit()
        summary = prove(workspace_for(project), findings, emit)
        run.summary_json = json.dumps(summary)
        run.safe_to_apply = bool(summary.get("generated_passed") and summary.get("regression_passed"))
        run.status = "passed" if run.safe_to_apply else "failed"
        run.finished_at = datetime.now(timezone.utc)
        record(session, project.id, "test_finished", f"Test run {run.status}.")
        session.commit()
    except Exception as exc:  # noqa: BLE001
        log.exception("test run failed")
        run = session.get(TestRun, run_id)
        if run:
            run.status = "error"
            run.summary_json = json.dumps({"error": str(exc)})
            run.finished_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        session.close()
