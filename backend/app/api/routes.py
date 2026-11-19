"""HTTP API. The React app talks only to these routes."""

from __future__ import annotations

import json
from collections import Counter

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.benchmark.runner import run_benchmark, sample_catalog
from app.config import settings
from app.db import SessionLocal, get_session
from app.exporting.report import render_pdf, report_payload, zip_workspace
from app.ids import new_id
from app.ingest.files import IngestError
from app.limiter import limit_request
from app.llm.gemini import GeminiError, translate_text
from app.models import Bug, HistoryEvent, Patch, Project, Scan, TestEvent, TestRun
from app.services import (
    apply_safe,
    create_from_github,
    create_from_sample,
    create_from_upload,
    decide_patch,
    latest_scan,
    run_scan,
    run_tests_job,
    workspace_for,
)

router = APIRouter(prefix="/api")


class SampleIn(BaseModel):
    sample_id: str = Field(min_length=1, max_length=80)


class GithubIn(BaseModel):
    url: str = Field(min_length=12, max_length=300)


class DecisionIn(BaseModel):
    action: str
    note: str = ""


class TranslateIn(BaseModel):
    language: str = Field(pattern="^(kn|hi|en)$")


def _project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found.")
    return project


def _bug_dict(session: Session, bug: Bug) -> dict:
    patches = session.scalars(select(Patch).where(Patch.bug_id == bug.id).order_by(Patch.created_at)).all()
    runs = session.scalars(select(TestRun).where(TestRun.project_id == bug.project_id).order_by(TestRun.created_at)).all()
    history = session.scalars(
        select(HistoryEvent).where(HistoryEvent.bug_id == bug.id).order_by(HistoryEvent.id)
    ).all()
    test_results = []
    for run in runs:
        summary = json.loads(run.summary_json or "{}")
        related = [
            item
            for item in summary.get("per_bug", [])
            if item.get("rule_id") == bug.rule_id and item.get("symbol") == bug.symbol and item.get("file") == bug.file
        ]
        if related or run.scan_id == bug.scan_id:
            test_results.append({"id": run.id, "status": run.status, "for_this_bug": related, "summary": summary})
    return {
        "id": bug.id,
        "scan_id": bug.scan_id,
        "bug_details": {
            "title": bug.title,
            "description": bug.description,
            "file": bug.file,
            "line": bug.line,
            "end_line": bug.end_line,
            "symbol": bug.symbol,
            "category": bug.category,
            "snippet": bug.snippet,
            "source": bug.source,
            "rule_id": bug.rule_id,
            "demo_cache_used": bug.demo_cache_used,
            "cached_root_cause": json.loads(bug.extra_json or "{}").get("cached_root_cause", ""),
        },
        "root_cause": bug.root_cause,
        "trigger": bug.trigger,
        "student_explanation": bug.student_explanation,
        "explanation_kn": bug.explanation_kn,
        "explanation_hi": bug.explanation_hi,
        "suggested_patch": [_patch_dict(patch) for patch in patches],
        "test_results": test_results,
        "severity_and_confidence": {
            "severity": bug.severity,
            "confidence": bug.confidence,
            "impact": bug.impact,
            "needs_human_review": bug.needs_human_review,
        },
        "change_history": [
            {"kind": event.kind, "message": event.message, "at": event.created_at.isoformat()} for event in history
        ],
    }


def _patch_dict(patch: Patch) -> dict:
    return {
        "id": patch.id,
        "bug_id": patch.bug_id,
        "file": patch.file,
        "diff": patch.diff,
        "before_code": patch.before_code,
        "after_code": patch.after_code,
        "status": patch.status,
        "source": patch.source,
        "confidence": patch.confidence,
    }


def _project_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "source_type": project.source_type,
        "sample_id": project.sample_id,
        "github_url": project.github_url,
        "created_at": project.created_at.isoformat(),
        "file_count": project.file_count,
        "languages": json.loads(project.languages_json or "[]"),
        "dependencies": json.loads(project.dependencies_json or "[]"),
        "important": json.loads(project.important_json or "[]"),
        "graph": json.loads(project.graph_json or "{}"),
        "tree": json.loads(project.tree_json or "[]"),
    }


def _scan_dict(scan: Scan) -> dict:
    return {
        "id": scan.id,
        "project_id": scan.project_id,
        "status": scan.status,
        "mode": scan.mode,
        "error": scan.error,
        "tool_notes": json.loads(scan.tool_notes_json or "[]"),
        "started_at": scan.started_at.isoformat(),
        "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
    }


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "gemini_configured": settings.gemini_configured,
        "demo_mode": not settings.gemini_configured,
        "database": "postgres" if settings.resolved_database_url.startswith("postgresql") else "sqlite",
    }


@router.get("/samples")
def samples() -> list[dict]:
    return sample_catalog()


@router.get("/projects")
def list_projects(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.scalars(select(Project).order_by(Project.created_at.desc())).all()
    return [_project_dict(row) for row in rows]


@router.post("/projects/sample", dependencies=[Depends(limit_request)])
def load_sample(body: SampleIn, session: Session = Depends(get_session)) -> dict:
    origin = settings.samples_dir / body.sample_id / "project"
    truth = settings.samples_dir / body.sample_id / "ground_truth.json"
    if not origin.is_dir() or not truth.is_file():
        raise HTTPException(404, "Unknown sample.")
    meta = json.loads(truth.read_text(encoding="utf-8"))
    try:
        project = create_from_sample(session, body.sample_id, meta["title"], origin)
    except IngestError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return _project_dict(project)


@router.post("/projects/upload", dependencies=[Depends(limit_request)])
async def upload(file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict:
    data = await file.read()
    try:
        project = create_from_upload(session, file.filename or "upload.txt", data)
    except IngestError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return _project_dict(project)


@router.post("/projects/github", dependencies=[Depends(limit_request)])
def from_github(body: GithubIn, session: Session = Depends(get_session)) -> dict:
    try:
        project = create_from_github(session, body.url)
    except IngestError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return _project_dict(project)


@router.get("/projects/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    return _project_dict(_project(session, project_id))


@router.get("/projects/{project_id}/file")
def read_file(project_id: str, path: str, session: Session = Depends(get_session)) -> dict:
    project = _project(session, project_id)
    root = workspace_for(project).resolve()
    target = (root / path).resolve()
    if target != root and root not in target.parents or not target.is_file():
        raise HTTPException(404, "File not found.")
    if target.stat().st_size > 200_000:
        raise HTTPException(400, "That file is too large to preview.")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "That file is not text.") from None
    return {"path": path, "text": text}


@router.post("/projects/{project_id}/scans", dependencies=[Depends(limit_request)])
def start_scan(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = _project(session, project_id)
    scan = run_scan(session, project)
    bugs = session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all()
    return {**_scan_dict(scan), "bugs": [_bug_dict(session, bug) for bug in bugs]}


@router.get("/projects/{project_id}/scans")
def list_scans(project_id: str, session: Session = Depends(get_session)) -> list[dict]:
    _project(session, project_id)
    rows = session.scalars(select(Scan).where(Scan.project_id == project_id).order_by(Scan.started_at.desc())).all()
    return [_scan_dict(row) for row in rows]


@router.get("/scans/{scan_id}")
def get_scan(scan_id: str, session: Session = Depends(get_session)) -> dict:
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found.")
    bugs = session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all()
    return {**_scan_dict(scan), "bugs": [_bug_dict(session, bug) for bug in bugs]}


@router.get("/bugs/{bug_id}")
def get_bug(bug_id: str, session: Session = Depends(get_session)) -> dict:
    bug = session.get(Bug, bug_id)
    if bug is None:
        raise HTTPException(404, "Bug not found.")
    return _bug_dict(session, bug)


@router.post("/bugs/{bug_id}/translate")
def translate(bug_id: str, body: TranslateIn, session: Session = Depends(get_session)) -> dict:
    bug = session.get(Bug, bug_id)
    if bug is None:
        raise HTTPException(404, "Bug not found.")
    if body.language == "en":
        return {"language": "en", "text": bug.student_explanation or bug.root_cause, "source": "stored"}
    stored = bug.explanation_kn if body.language == "kn" else bug.explanation_hi
    if stored:
        return {"language": body.language, "text": stored, "source": "stored"}
    try:
        text = translate_text(bug.student_explanation or bug.root_cause, body.language)
    except GeminiError as exc:
        raise HTTPException(503, f"Translation needs Gemini. {exc}") from exc
    if body.language == "kn":
        bug.explanation_kn = text
    else:
        bug.explanation_hi = text
    session.commit()
    return {"language": body.language, "text": text, "source": "gemini"}


@router.post("/patches/{patch_id}/decision")
def decision(patch_id: str, body: DecisionIn, session: Session = Depends(get_session)) -> dict:
    patch = session.get(Patch, patch_id)
    if patch is None:
        raise HTTPException(404, "Patch not found.")
    try:
        patch = decide_patch(session, patch, body.action, body.note)
    except IngestError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return _patch_dict(patch)


@router.post("/scans/{scan_id}/apply-safe")
def safe(scan_id: str, session: Session = Depends(get_session)) -> dict:
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found.")
    project = _project(session, scan.project_id)
    try:
        return apply_safe(session, project, scan)
    except IngestError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/projects/{project_id}/tests", dependencies=[Depends(limit_request)])
def start_tests(project_id: str, background: BackgroundTasks, session: Session = Depends(get_session)) -> dict:
    project = _project(session, project_id)
    scan = latest_scan(session, project.id)
    if scan is None:
        raise HTTPException(400, "Scan the project before running tests.")
    run = TestRun(id=new_id(), project_id=project.id, scan_id=scan.id, status="queued")
    session.add(run)
    session.commit()
    background.add_task(run_tests_job, run.id)
    return {"id": run.id, "status": run.status}


@router.get("/test-runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    run = session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(404, "Test run not found.")
    events = session.scalars(select(TestEvent).where(TestEvent.test_run_id == run.id).order_by(TestEvent.id)).all()
    return {
        "id": run.id,
        "status": run.status,
        "safe_to_apply": run.safe_to_apply,
        "summary": json.loads(run.summary_json or "{}"),
        "events": [{"id": event.id, "message": event.message, "status": event.status} for event in events],
    }


@router.get("/test-runs/{run_id}/events")
async def stream_events(run_id: str, request: Request):
    import asyncio

    session = SessionLocal()
    try:
        if session.get(TestRun, run_id) is None:
            raise HTTPException(404, "Test run not found.")
    finally:
        session.close()

    async def gen():
        last = 0
        while True:
            if await request.is_disconnected():
                break
            current = SessionLocal()
            try:
                rows = current.scalars(
                    select(TestEvent).where(TestEvent.test_run_id == run_id, TestEvent.id > last).order_by(TestEvent.id)
                ).all()
                run = current.get(TestRun, run_id)
                for event in rows:
                    last = event.id
                    payload = json.dumps({"id": event.id, "message": event.message, "status": event.status})
                    yield f"data: {payload}\n\n"
                if run and run.status in {"passed", "failed", "error"} and (rows or last):
                    yield f"event: done\ndata: {json.dumps({'status': run.status})}\n\n"
                    break
                if run and run.status in {"passed", "failed", "error"} and not rows and last == 0:
                    yield f"event: done\ndata: {json.dumps({'status': run.status})}\n\n"
                    break
            finally:
                current.close()
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/projects/{project_id}/history")
def history(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = _project(session, project_id)
    events = session.scalars(
        select(HistoryEvent).where(HistoryEvent.project_id == project.id).order_by(HistoryEvent.id)
    ).all()
    scans = session.scalars(select(Scan).where(Scan.project_id == project.id).order_by(Scan.started_at)).all()
    return {
        "project": _project_dict(project),
        "events": [
            {"kind": event.kind, "message": event.message, "bug_id": event.bug_id, "at": event.created_at.isoformat()}
            for event in events
        ],
        "scans": [_scan_dict(scan) for scan in scans],
    }


@router.get("/projects/{project_id}/dashboard")
def dashboard(project_id: str, session: Session = Depends(get_session)) -> dict:
    project = _project(session, project_id)
    scan = latest_scan(session, project.id)
    bugs = []
    if scan:
        bugs = list(session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all())
    by_severity = Counter(bug.severity for bug in bugs)
    by_category = Counter(bug.category for bug in bugs)
    review = sum(1 for bug in bugs if bug.needs_human_review)
    actionable = [bug for bug in bugs if bug.category != "style" and bug.severity != "low"]
    return {
        "project": _project_dict(project),
        "scan": None if scan is None else _scan_dict(scan),
        "counts": {
            "findings": len(bugs),
            "actionable": len(actionable),
            "needs_review": review,
            "by_severity": dict(by_severity),
            "by_category": dict(by_category),
        },
        "bugs": [
            {
                "id": bug.id,
                "title": bug.title,
                "severity": bug.severity,
                "confidence": bug.confidence,
                "category": bug.category,
                "needs_human_review": bug.needs_human_review,
                "file": bug.file,
            }
            for bug in bugs
        ],
    }


@router.get("/projects/{project_id}/export/json")
def export_json(project_id: str, session: Session = Depends(get_session)):
    project = _project(session, project_id)
    payload = report_payload(session, project, latest_scan(session, project.id))
    return Response(content=json.dumps(payload, indent=2), media_type="application/json")


@router.get("/projects/{project_id}/export/pdf")
def export_pdf(project_id: str, session: Session = Depends(get_session)):
    project = _project(session, project_id)
    payload = report_payload(session, project, latest_scan(session, project.id))
    return Response(
        content=render_pdf(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{project.name}.pdf"'},
    )


@router.get("/projects/{project_id}/export/zip")
def export_zip(project_id: str, session: Session = Depends(get_session)):
    project = _project(session, project_id)
    return Response(
        content=zip_workspace(project),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project.name}-fixed.zip"'},
    )


@router.get("/benchmark")
def benchmark_cached() -> dict:
    path = settings.repo_root / "benchmark" / "results" / "latest.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"projects": [], "note": "No measured results yet. Run the benchmark."}


@router.post("/benchmark/run", dependencies=[Depends(limit_request)])
def benchmark_run() -> dict:
    result = run_benchmark()
    path = settings.repo_root / "benchmark" / "results"
    path.mkdir(parents=True, exist_ok=True)
    (path / "latest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
