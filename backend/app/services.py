"""Create projects, run scans, record decisions. Routes stay thin."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.pipeline import analyze_project
from app.ids import new_id
from app.ingest.files import IngestError, copy_project, extract_tar, extract_zip, project_paths, write_files
from app.ingest.formats import extract_upload, is_archive, sniff
from app.ingest.github import download_github
from app.ingest.links import fetch_gist, resolve_link, safe_get
from app.ingest.structure import describe_project
from app.models import (
    Bug,
    Decision,
    HistoryEvent,
    Patch,
    Project,
    Scan,
    TestRun,
    User,
    WorkspaceVersion,
)
from app.patching.diffgen import changed_region, unified_diff
from app.patching.fixers import propose_fix
from app.testing.service import prove

log = logging.getLogger(__name__)

_SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_RISKY_KEYWORDS = (
    "auth",
    "password",
    "token",
    "secret",
    "sql",
    "database",
    "money",
    "payment",
    "balance",
    "withdraw",
    "deposit",
    "security",
    "crypto",
    "jwt",
    "session",
)


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


def _attach_owner(project: Project, user: User | None) -> None:
    if user is None:
        project.user_id = None
        project.is_guest = True
    else:
        project.user_id = user.id
        project.is_guest = False


def _ensure_v0(session: Session, project: Project) -> None:
    existing = session.scalar(
        select(WorkspaceVersion).where(WorkspaceVersion.project_id == project.id, WorkspaceVersion.version == 0)
    )
    if existing:
        return
    session.add(
        WorkspaceVersion(
            id=new_id(),
            project_id=project.id,
            version=0,
            label="v0 original",
            path=f"projects/{project.id}/source",
        )
    )


def create_from_sample(
    session: Session, sample_id: str, title: str, origin: Path, user: User | None = None
) -> Project:
    project = Project(id=new_id(), name=title, source_type="sample", sample_id=sample_id)
    _attach_owner(project, user)
    session.add(project)
    session.flush()
    workspace = copy_project(origin, project.id)
    _store_meta(project, workspace)
    _ensure_v0(session, project)
    record(session, project.id, "upload", f"Loaded sample “{title}”.")
    session.commit()
    return project


def create_from_upload(session: Session, filename: str, data: bytes, user: User | None = None) -> Project:
    archive = is_archive(filename, data)
    project = Project(
        id=new_id(),
        name=_display_name(filename),
        source_type="zip" if archive else "upload",
    )
    _attach_owner(project, user)
    session.add(project)
    session.flush()
    workspace = ingest_bytes(project.id, filename, data)
    _store_meta(project, workspace)
    _ensure_v0(session, project)
    record(session, project.id, "upload", f"Uploaded {Path(filename).name}.")
    session.commit()
    return project


def ingest_bytes(project_id: str, filename: str, data: bytes) -> Path:
    """Unpack an archive, or convert any other upload into source files."""
    if is_archive(filename, data):
        if sniff(data) == "zip":
            return extract_zip(project_id, data)
        return extract_tar(project_id, data)
    extraction = extract_upload(filename, data)
    return write_files(project_id, [(item.path, item.content) for item in extraction.files])


PASTE_ORIGINS = {"paste", "upload", "pdf", "image", "notebook", "docx", "code"}


def create_from_files(
    session: Session,
    name: str,
    files: list[tuple[str, str]],
    origin: str = "paste",
    user: User | None = None,
) -> Project:
    """Create a project from pasted code or a confirmed extraction preview."""
    source_type = origin if origin in PASTE_ORIGINS else "paste"
    project = Project(id=new_id(), name=(name.strip() or "pasted-code")[:120], source_type=source_type)
    _attach_owner(project, user)
    session.add(project)
    session.flush()
    workspace = write_files(project.id, files)
    _store_meta(project, workspace)
    _ensure_v0(session, project)
    label = "Pasted code" if source_type == "paste" else f"Confirmed {source_type} extraction"
    record(session, project.id, "upload", f"{label}: {len(files)} file(s).")
    session.commit()
    return project


def create_from_link(session: Session, url: str, user: User | None = None) -> Project:
    link = resolve_link(url)
    if link.kind == "repo":
        return create_from_github(session, link.url, user=user)
    if link.kind == "gist":
        files = fetch_gist(link.url)
        name = Path(files[0][0]).stem or "gist"
    else:
        data = safe_get(link.url)
        files = None
        name = _display_name(link.filename)
    project = Project(id=new_id(), name=name[:120], source_type="link", github_url=url.strip()[:300])
    _attach_owner(project, user)
    session.add(project)
    session.flush()
    if files is not None:
        workspace = write_files(project.id, files)
    else:
        workspace = ingest_bytes(project.id, link.filename, data)
    _store_meta(project, workspace)
    _ensure_v0(session, project)
    record(session, project.id, "upload", f"Imported {url.strip()[:200]}.")
    session.commit()
    return project


def _display_name(filename: str) -> str:
    name = Path(filename).name
    for suffix in (".tar.gz", ".tgz", ".tar", ".zip"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)] or "upload"
    return Path(name).stem or "upload"


def create_from_github(session: Session, url: str, user: User | None = None) -> Project:
    origin = download_github(url)
    try:
        project = Project(id=new_id(), name=url.rstrip("/").split("/")[-1], source_type="github", github_url=url)
        _attach_owner(project, user)
        session.add(project)
        session.flush()
        workspace = copy_project(origin, project.id)
        _store_meta(project, workspace)
        _ensure_v0(session, project)
        record(session, project.id, "upload", f"Cloned {url}.")
        session.commit()
        return project
    finally:
        shutil.rmtree(origin.parent, ignore_errors=True)


def workspace_for(project: Project) -> Path:
    _source, workspace = project_paths(project.id)
    return workspace


def source_for(project: Project) -> Path:
    source, _workspace = project_paths(project.id)
    return source


def versions_dir(project_id: str) -> Path:
    path = settings_data_projects(project_id) / "versions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_data_projects(project_id: str) -> Path:
    from app.config import settings

    return settings.data_dir / "projects" / project_id


def latest_version_number(session: Session, project_id: str) -> int:
    value = session.scalar(
        select(func.max(WorkspaceVersion.version)).where(WorkspaceVersion.project_id == project_id)
    )
    return int(value or 0)


def snapshot_workspace(session: Session, project: Project, label: str, patch_id: str | None = None) -> WorkspaceVersion:
    next_ver = latest_version_number(session, project.id) + 1
    dest = versions_dir(project.id) / f"v{next_ver}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(workspace_for(project), dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    row = WorkspaceVersion(
        id=new_id(),
        project_id=project.id,
        version=next_ver,
        label=label,
        patch_id=patch_id,
        path=f"projects/{project.id}/versions/v{next_ver}",
    )
    session.add(row)
    session.flush()
    return row


def restore_version_files(project: Project, version: int) -> None:
    workspace = workspace_for(project)
    if version <= 0:
        origin = source_for(project)
    else:
        origin = versions_dir(project.id) / f"v{version}"
        if not origin.is_dir():
            raise IngestError(f"Version v{version} was not found.", status=404)
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(origin, workspace)


def risk_level(bug: Bug) -> str:
    haystack = " ".join(
        [
            bug.file or "",
            bug.title or "",
            bug.category or "",
            bug.rule_id or "",
            bug.description or "",
            bug.impact or "",
        ]
    ).lower()
    if bug.category == "security" or any(word in haystack for word in _RISKY_KEYWORDS):
        return "risky"
    if bug.needs_human_review or bug.confidence < 0.8 or bug.severity in {"critical", "high"}:
        return "review carefully"
    return "safe"


def run_scan(session: Session, project: Project, user: User | None = None) -> Scan:
    scan = Scan(
        id=new_id(),
        project_id=project.id,
        user_id=user.id if user else project.user_id,
        status="running",
    )
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
        _propose_patch(session, project, bug, workspace, user)
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


def _propose_patch(
    session: Session, project: Project, bug: Bug, workspace: Path, user: User | None = None
) -> None:
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
        user_id=user.id if user else project.user_id,
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


def _decision_action(action: str) -> str:
    mapping = {
        "accept": "approved",
        "approve": "approved",
        "reject": "rejected",
        "edit": "edited",
        "skip": "skipped",
        "auto": "auto-applied",
        "auto-applied": "auto-applied",
    }
    if action not in mapping and action not in mapping.values():
        raise IngestError("Decision must be approve, reject, edit, skip, or accept.")
    return mapping.get(action, action)


def _write_patch_content(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _verify_workspace_tests(project: Project, bug: Bug | None) -> tuple[bool, dict]:
    """Quick proof after applying one fix. Returns (ok, summary)."""
    from app.analysis.findings import Finding

    findings: list[Finding] = []
    if bug is not None:
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
    try:
        summary = prove(workspace_for(project), findings, emit=None)
    except Exception as exc:  # noqa: BLE001
        log.exception("post-fix verify failed")
        return False, {"error": str(exc), "regression_passed": False, "generated_passed": False}
    ok = bool(summary.get("regression_passed"))
    return ok, summary


def decide_patch(
    session: Session,
    patch: Patch,
    action: str,
    note: str = "",
    user: User | None = None,
    edited_code: str | None = None,
    verify_tests: bool = False,
) -> dict:
    """Apply a human decision. Returns patch dict fields plus optional rollback info."""
    normalized = _decision_action(action)
    if patch.status in {"applied", "rejected", "skipped"} and normalized != "rolled_back":
        raise IngestError(f"This patch is already {patch.status}.")

    project = session.get(Project, patch.project_id)
    bug = session.get(Bug, patch.bug_id)
    if project is None:
        raise IngestError("Patch is missing its project.", status=404)

    user_id = user.id if user else patch.user_id or project.user_id

    if normalized == "rejected":
        patch.status = "rejected"
        session.add(
            Decision(
                id=new_id(),
                patch_id=patch.id,
                project_id=patch.project_id,
                user_id=user_id,
                action="rejected",
                note=note,
            )
        )
        record(
            session,
            patch.project_id,
            "rejected",
            f"Rejected the patch for {bug.title if bug else patch.file}.",
            bug.id if bug else None,
        )
        session.commit()
        return {"patch": patch, "rolled_back": False, "test_summary": None}

    if normalized == "skipped":
        patch.status = "skipped"
        session.add(
            Decision(
                id=new_id(),
                patch_id=patch.id,
                project_id=patch.project_id,
                user_id=user_id,
                action="skipped",
                note=note,
            )
        )
        record(
            session,
            patch.project_id,
            "skipped",
            f"Skipped the patch for {bug.title if bug else patch.file}.",
            bug.id if bug else None,
        )
        session.commit()
        return {"patch": patch, "rolled_back": False, "test_summary": None}

    if bug is None:
        raise IngestError("Patch is missing its bug.", status=404)

    workspace = workspace_for(project)
    path = workspace / bug.file
    if not path.is_file():
        raise IngestError("The target file is missing from the workspace.")

    # Snapshot current workspace before mutating so we can roll back.
    before_version = latest_version_number(session, project.id)
    previous_text = path.read_text(encoding="utf-8")

    if normalized == "edited":
        if not edited_code:
            raise IngestError("Edited code is required when editing a patch.")
        # Prefer replacing the known before-region; fall back to full-file replacement.
        if patch.before_code and patch.before_code in previous_text:
            updated = previous_text.replace(patch.before_code, edited_code, 1)
        elif edited_code.strip() == previous_text.strip() or len(edited_code) > len(previous_text) // 2:
            updated = edited_code
        else:
            # Treat edited_code as a new after-snippet when before is unavailable.
            proposed = propose_fix(previous_text, bug.rule_id, bug.symbol, json.loads(bug.extra_json or "{}"))
            if proposed and patch.after_code and patch.after_code in proposed:
                updated = proposed.replace(patch.after_code, edited_code, 1)
            else:
                updated = edited_code
        decision_action = "edited"
    else:
        updated = propose_fix(previous_text, bug.rule_id, bug.symbol, json.loads(bug.extra_json or "{}"))
        if not updated:
            raise IngestError("The patch no longer applies. The file may already be fixed.")
        decision_action = "approved" if normalized == "approved" else normalized

    _write_patch_content(path, updated)
    patch.diff = unified_diff(bug.file, previous_text, updated)
    before, after = changed_region(previous_text, updated)
    patch.before_code = before
    patch.after_code = after
    patch.status = "applied"

    rolled_back = False
    test_summary = None
    if verify_tests:
        ok, test_summary = _verify_workspace_tests(project, bug)
        if not ok:
            _write_patch_content(path, previous_text)
            patch.status = "proposed"
            patch.diff = unified_diff(bug.file, previous_text, updated)
            patch.before_code = before
            patch.after_code = after
            session.add(
                Decision(
                    id=new_id(),
                    patch_id=patch.id,
                    project_id=project.id,
                    user_id=user_id,
                    action="rolled_back",
                    note=note or "Auto-rolled back because tests failed after apply.",
                )
            )
            record(
                session,
                project.id,
                "rolled_back",
                f"Auto-rolled back {bug.title}: tests failed after the fix.",
                bug.id,
            )
            session.commit()
            return {"patch": patch, "rolled_back": True, "test_summary": test_summary}

    snapshot_workspace(
        session,
        project,
        label=f"v{before_version + 1} after {decision_action}: {bug.title}",
        patch_id=patch.id,
    )
    session.add(
        Decision(
            id=new_id(),
            patch_id=patch.id,
            project_id=project.id,
            user_id=user_id,
            action=decision_action,
            note=note,
        )
    )
    record(
        session,
        project.id,
        decision_action,
        f"{decision_action.capitalize()} and applied the patch for {bug.title}.",
        bug.id,
    )
    session.commit()
    return {"patch": patch, "rolled_back": rolled_back, "test_summary": test_summary}


def regenerate_fix_after_rejection(session: Session, patch: Patch, reason: str) -> dict:
    """Ask Gemini for an alternative explanation/fix hint after a rejection with a reason."""
    from app.llm.gemini import GeminiError, _generate
    from app.config import settings

    bug = session.get(Bug, patch.bug_id)
    if bug is None:
        raise IngestError("Bug not found.", status=404)
    if not settings.gemini_configured:
        return {
            "available": False,
            "message": "Gemini is not configured. Your rejection reason was saved; try another fix later with a key set.",
            "alternative": None,
        }
    prompt = (
        "A human rejected an automated bug fix. Suggest an alternative approach in plain English "
        "and, if possible, a short corrected code snippet for ONLY the changed lines.\n"
        f"File: {bug.file}:{bug.line}\nTitle: {bug.title}\nRoot cause: {bug.root_cause}\n"
        f"Previous after-code:\n{patch.after_code}\n\nRejection reason: {reason}\n"
        'Return JSON: {"explanation": "...", "after_code": "..."}'
    )
    try:
        raw = _generate(settings.gemini_model, prompt)
    except GeminiError as exc:
        return {"available": False, "message": str(exc), "alternative": None}
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {"explanation": text, "after_code": ""}
    return {
        "available": True,
        "message": "Alternative fix suggestion ready.",
        "alternative": {
            "explanation": payload.get("explanation", ""),
            "after_code": payload.get("after_code", ""),
        },
    }


def apply_safe(
    session: Session,
    project: Project,
    scan: Scan,
    user: User | None = None,
    mode: str = "safe",
    dry_run: bool = False,
) -> dict:
    """Apply safe fixes. mode=safe uses existing gates; mode=auto_safe requires confidence>=0.9."""
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
    planned = []
    workspace = workspace_for(project)
    min_confidence = 0.9 if mode == "auto_safe" else 0.8
    user_id = user.id if user else project.user_id

    for bug in bugs:
        patch = session.scalar(select(Patch).where(Patch.bug_id == bug.id).order_by(Patch.created_at.desc()))
        if patch is None or patch.status != "proposed":
            continue
        key = (bug.file, bug.rule_id, bug.symbol)
        level = risk_level(bug)
        safe = (
            bug.confidence >= min_confidence
            and not bug.needs_human_review
            and key in passed_keys
            and "cached_demo" not in (bug.source or "")
            and level == "safe"
        )
        if mode == "safe":
            # Preserve prior behaviour for "Apply all safe fixes": confidence>=0.8, not necessarily risk==safe
            safe = (
                bug.confidence >= 0.8
                and not bug.needs_human_review
                and key in passed_keys
                and "cached_demo" not in (bug.source or "")
            )
        if not safe:
            skipped.append(
                {
                    "bug_id": bug.id,
                    "title": bug.title,
                    "reason": "low confidence, needs review, risky, or its test did not pass",
                    "risk": level,
                }
            )
            continue
        planned.append(
            {
                "bug_id": bug.id,
                "patch_id": patch.id,
                "title": bug.title,
                "file": bug.file,
                "line": bug.line,
                "confidence": bug.confidence,
                "risk": level,
                "before_code": patch.before_code,
                "after_code": patch.after_code,
            }
        )
        if dry_run:
            continue
        path = workspace / bug.file
        source = path.read_text(encoding="utf-8")
        updated = propose_fix(source, bug.rule_id, bug.symbol, json.loads(bug.extra_json or "{}"))
        if not updated:
            skipped.append({"bug_id": bug.id, "title": bug.title, "reason": "patch did not apply cleanly"})
            continue
        path.write_text(updated, encoding="utf-8")
        patch.status = "applied"
        session.add(
            Decision(
                id=new_id(),
                patch_id=patch.id,
                project_id=project.id,
                user_id=user_id,
                action="auto-applied",
                note="Applied by safe-fix. Tests passed and confidence was high.",
            )
        )
        snapshot_workspace(session, project, label=f"Safe fix: {bug.title}", patch_id=patch.id)
        record(session, project.id, "accepted", f"Safe fix applied: {bug.title}.", bug.id)
        applied.append({"bug_id": bug.id, "title": bug.title, "file": bug.file})
    if not dry_run:
        session.commit()
    return {"applied": applied, "skipped": skipped, "planned": planned, "dry_run": dry_run}


def rollback_last(session: Session, project: Project, user: User | None = None) -> dict:
    current = latest_version_number(session, project.id)
    if current <= 0:
        raise IngestError("Nothing to undo. The workspace is still at the original upload.")
    target = current - 1
    restore_version_files(project, target)
    # Reset the patch tied to the rolled-back version, if any.
    version_row = session.scalar(
        select(WorkspaceVersion).where(
            WorkspaceVersion.project_id == project.id, WorkspaceVersion.version == current
        )
    )
    if version_row and version_row.patch_id:
        patch = session.get(Patch, version_row.patch_id)
        if patch and patch.status == "applied":
            patch.status = "proposed"
            session.add(
                Decision(
                    id=new_id(),
                    patch_id=patch.id,
                    project_id=project.id,
                    user_id=user.id if user else project.user_id,
                    action="rolled_back",
                    note="Undo last fix.",
                )
            )
    # Drop the newest version record (files stay on disk but are unused).
    if version_row:
        session.delete(version_row)
    record(session, project.id, "rollback", f"Undid last fix. Workspace restored to v{target}.")
    session.commit()
    return {"version": target, "message": f"Restored to v{target}."}


def rollback_all(session: Session, project: Project, user: User | None = None) -> dict:
    restore_version_files(project, 0)
    patches = session.scalars(
        select(Patch).where(Patch.project_id == project.id, Patch.status == "applied")
    ).all()
    for patch in patches:
        patch.status = "proposed"
        session.add(
            Decision(
                id=new_id(),
                patch_id=patch.id,
                project_id=project.id,
                user_id=user.id if user else project.user_id,
                action="rolled_back",
                note="Rollback all fixes to original upload.",
            )
        )
    # Keep v0; remove higher version rows.
    extras = session.scalars(
        select(WorkspaceVersion).where(WorkspaceVersion.project_id == project.id, WorkspaceVersion.version > 0)
    ).all()
    for row in extras:
        session.delete(row)
    versions_root = versions_dir(project.id)
    if versions_root.exists():
        shutil.rmtree(versions_root)
        versions_root.mkdir(parents=True, exist_ok=True)
    record(session, project.id, "rollback", "Rolled back all fixes to the original upload (v0).")
    session.commit()
    return {"version": 0, "message": "Restored to v0 original.", "reset_patches": len(patches)}


def list_versions(session: Session, project_id: str) -> list[dict]:
    rows = session.scalars(
        select(WorkspaceVersion).where(WorkspaceVersion.project_id == project_id).order_by(WorkspaceVersion.version)
    ).all()
    return [
        {
            "id": row.id,
            "version": row.version,
            "label": row.label,
            "patch_id": row.patch_id,
            "path": row.path,
            "at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def decision_log(session: Session, project_id: str) -> list[dict]:
    rows = session.scalars(
        select(Decision).where(Decision.project_id == project_id).order_by(Decision.created_at)
    ).all()
    result = []
    for row in rows:
        user = session.get(User, row.user_id) if row.user_id else None
        patch = session.get(Patch, row.patch_id)
        result.append(
            {
                "id": row.id,
                "fix_id": row.patch_id,
                "decision": row.action,
                "note": row.note,
                "user_id": row.user_id,
                "coder_id": user.coder_id if user else None,
                "who": user.full_name if user else ("Guest" if not row.user_id else row.user_id),
                "file": patch.file if patch else None,
                "timestamp": row.created_at.isoformat(),
            }
        )
    return result


def profile_stats(session: Session, user: User) -> dict:
    project_ids = list(session.scalars(select(Project.id).where(Project.user_id == user.id)).all())
    if not project_ids:
        return {
            "total_scans": 0,
            "bugs_found": 0,
            "patches_accepted": 0,
            "patches_rejected": 0,
            "member_since": user.created_at.isoformat(),
        }
    total_scans = session.scalar(select(func.count()).select_from(Scan).where(Scan.user_id == user.id)) or 0
    # Prefer scan.user_id; also count bugs on owned projects for older rows.
    bugs_found = (
        session.scalar(select(func.count()).select_from(Bug).where(Bug.project_id.in_(project_ids))) or 0
    )
    accepted = (
        session.scalar(
            select(func.count())
            .select_from(Decision)
            .where(Decision.user_id == user.id, Decision.action.in_(["approved", "accept", "auto-applied", "edited"]))
        )
        or 0
    )
    rejected = (
        session.scalar(
            select(func.count())
            .select_from(Decision)
            .where(Decision.user_id == user.id, Decision.action.in_(["rejected", "reject"]))
        )
        or 0
    )
    return {
        "total_scans": int(total_scans),
        "bugs_found": int(bugs_found),
        "patches_accepted": int(accepted),
        "patches_rejected": int(rejected),
        "member_since": user.created_at.isoformat(),
    }


def fix_progress(session: Session, scan_id: str) -> dict:
    bugs = session.scalars(select(Bug).where(Bug.scan_id == scan_id)).all()
    patches = []
    for bug in bugs:
        patch = session.scalar(select(Patch).where(Patch.bug_id == bug.id).order_by(Patch.created_at.desc()))
        if patch:
            patches.append((bug, patch))
    total = len(patches)
    approved = sum(1 for _, p in patches if p.status == "applied")
    rejected = sum(1 for _, p in patches if p.status == "rejected")
    skipped = sum(1 for _, p in patches if p.status == "skipped")
    proposed = [pair for pair in patches if pair[1].status == "proposed"]
    current_index = approved + rejected + skipped
    return {
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "skipped": skipped,
        "remaining": len(proposed),
        "current": current_index + 1 if proposed else total,
        "label": f"Fix {min(current_index + 1, total)} of {total}" if total else "No fixes",
    }


def health_score(session: Session, project: Project, scan: Scan | None) -> dict:
    """Simple 0–100 health score from severity mix and patch status."""
    if scan is None:
        return {"before": 100, "after": 100}
    bugs = list(session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all())
    if not bugs:
        return {"before": 100, "after": 100}
    weight = {"critical": 25, "high": 15, "medium": 8, "low": 3}
    penalty = sum(weight.get(bug.severity, 5) for bug in bugs)
    before = max(0, 100 - penalty)
    remaining = 0
    for bug in bugs:
        patch = session.scalar(select(Patch).where(Patch.bug_id == bug.id).order_by(Patch.created_at.desc()))
        if patch is None or patch.status != "applied":
            if bug.category != "style":
                remaining += weight.get(bug.severity, 5)
    after = max(0, 100 - remaining)
    return {"before": before, "after": after}


def latest_scan(session: Session, project_id: str) -> Scan | None:
    return session.scalar(select(Scan).where(Scan.project_id == project_id).order_by(Scan.started_at.desc()))


def user_can_access(project: Project, user: User | None) -> bool:
    if user is None:
        return True  # guest / demo: opaque project id is the capability
    if user.role == "admin":
        return True
    if project.user_id is None or project.is_guest:
        return True  # guest projects remain reachable by id
    return project.user_id == user.id


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
