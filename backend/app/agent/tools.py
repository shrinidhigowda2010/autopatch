"""Tools the FixPilot Assistant can call while chatting about a project."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.redaction import redact_path_name, redact_text
from app.models import Bug, Patch, Project, TestRun
from app.services import latest_scan, workspace_for

TOOL_DECLARATIONS = [
    {
        "name": "scan_file",
        "description": "Read a project source file (secrets redacted) and summarize what is in it.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Relative file path in the workspace"}},
            "required": ["path"],
        },
    },
    {
        "name": "explain_bug",
        "description": "Explain a known bug from the latest scan by bug id.",
        "parameters": {
            "type": "object",
            "properties": {"bug_id": {"type": "string"}},
            "required": ["bug_id"],
        },
    },
    {
        "name": "propose_fix",
        "description": "Return the proposed patch for a bug (diff + before/after). Does not apply it.",
        "parameters": {
            "type": "object",
            "properties": {"bug_id": {"type": "string"}},
            "required": ["bug_id"],
        },
    },
    {
        "name": "run_tests",
        "description": "Return the latest test-run summary for this project (does not start a new long job).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "show_diff",
        "description": "Show a patch diff by patch id.",
        "parameters": {
            "type": "object",
            "properties": {"fix_id": {"type": "string"}},
            "required": ["fix_id"],
        },
    },
    {
        "name": "search_code",
        "description": "Search project source files for a query string.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def tool_label(name: str, args: dict) -> str:
    if name == "scan_file":
        return f"Scanning {args.get('path', 'file')}..."
    if name == "explain_bug":
        return f"Explaining bug {args.get('bug_id', '')}..."
    if name == "propose_fix":
        return f"Proposing fix for {args.get('bug_id', '')}..."
    if name == "run_tests":
        return "Running tests..."
    if name == "show_diff":
        return f"Loading diff {args.get('fix_id', '')}..."
    if name == "search_code":
        return f"Searching for “{args.get('query', '')}”..."
    return f"Using {name}..."


def execute_tool(session: Session, project: Project, name: str, args: dict) -> tuple[dict, dict | None]:
    """Run a tool. Returns (result_payload, optional_patch_card)."""
    workspace = workspace_for(project)
    if name == "scan_file":
        return _scan_file(workspace, str(args.get("path") or "")), None
    if name == "explain_bug":
        return _explain_bug(session, project, str(args.get("bug_id") or "")), None
    if name == "propose_fix":
        return _propose_fix(session, project, str(args.get("bug_id") or ""))
    if name == "run_tests":
        return _run_tests(session, project), None
    if name == "show_diff":
        return _show_diff(session, project, str(args.get("fix_id") or ""))
    if name == "search_code":
        return _search_code(workspace, str(args.get("query") or "")), None
    return {"error": f"Unknown tool: {name}"}, None


def _safe_path(workspace: Path, rel: str) -> Path | None:
    rel = (rel or "").lstrip("/").replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        return None
    if redact_path_name(rel):
        return None
    target = (workspace / rel).resolve()
    if target != workspace.resolve() and workspace.resolve() not in target.parents:
        return None
    return target if target.is_file() else None


def _scan_file(workspace: Path, rel: str) -> dict:
    path = _safe_path(workspace, rel)
    if path is None:
        return {"error": "File not found or blocked (secrets/.env)."}
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"error": "Could not read that file as text."}
    text = redact_text(raw)
    return {"path": rel, "bytes": len(text), "content": text[:12000]}


def _explain_bug(session: Session, project: Project, bug_id: str) -> dict:
    bug = session.get(Bug, bug_id)
    if bug is None or bug.project_id != project.id:
        return {"error": "Bug not found in this project."}
    return {
        "bug_id": bug.id,
        "title": bug.title,
        "file": bug.file,
        "line": bug.line,
        "severity": bug.severity,
        "confidence": bug.confidence,
        "root_cause": bug.root_cause,
        "trigger": bug.trigger,
        "student_explanation": bug.student_explanation,
        "category": bug.category,
    }


def _propose_fix(session: Session, project: Project, bug_id: str) -> tuple[dict, dict | None]:
    bug = session.get(Bug, bug_id)
    if bug is None or bug.project_id != project.id:
        return {"error": "Bug not found in this project."}, None
    patch = session.scalar(select(Patch).where(Patch.bug_id == bug.id).order_by(Patch.created_at.desc()))
    if patch is None:
        return {"error": "No proposed patch for this bug yet. Run a scan first."}, None
    card = {
        "patch_id": patch.id,
        "bug_id": bug.id,
        "title": bug.title,
        "file": patch.file,
        "status": patch.status,
        "diff": patch.diff,
        "before_code": patch.before_code,
        "after_code": patch.after_code,
        "confidence": patch.confidence,
    }
    return {
        "bug_id": bug.id,
        "patch_id": patch.id,
        "status": patch.status,
        "file": patch.file,
        "diff": patch.diff,
        "message": "Patch is ready for human approval. It has not been applied.",
    }, card


def _run_tests(session: Session, project: Project) -> dict:
    run = session.scalar(select(TestRun).where(TestRun.project_id == project.id).order_by(TestRun.created_at.desc()))
    if run is None:
        return {
            "status": "none",
            "message": "No test run yet. Ask the user to open the Test page, or summarize that tests have not been run.",
        }
    summary = json.loads(run.summary_json or "{}")
    per_bug = summary.get("per_bug") or []
    passed = sum(1 for item in per_bug if item.get("passed"))
    failed = sum(1 for item in per_bug if item.get("passed") is False)
    return {
        "status": run.status,
        "safe_to_apply": run.safe_to_apply,
        "passed": passed,
        "failed": failed,
        "regression_passed": summary.get("regression_passed"),
        "generated_passed": summary.get("generated_passed"),
        "summary": summary,
    }


def _show_diff(session: Session, project: Project, patch_id: str) -> tuple[dict, dict | None]:
    patch = session.get(Patch, patch_id)
    if patch is None or patch.project_id != project.id:
        return {"error": "Patch not found."}, None
    bug = session.get(Bug, patch.bug_id)
    card = {
        "patch_id": patch.id,
        "bug_id": patch.bug_id,
        "title": bug.title if bug else patch.file,
        "file": patch.file,
        "status": patch.status,
        "diff": patch.diff,
        "before_code": patch.before_code,
        "after_code": patch.after_code,
        "confidence": patch.confidence,
    }
    return {"patch_id": patch.id, "file": patch.file, "status": patch.status, "diff": patch.diff}, card


def _search_code(workspace: Path, query: str) -> dict:
    query = (query or "").strip()
    if len(query) < 2:
        return {"error": "Query too short."}
    hits = []
    for path in workspace.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(workspace).as_posix()
        if redact_path_name(rel):
            continue
        if path.suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".jsx", ".txt", ".md", ".json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = redact_text(text)
        for i, line in enumerate(text.splitlines(), start=1):
            if query.lower() in line.lower():
                hits.append({"path": rel, "line": i, "text": line.strip()[:200]})
                if len(hits) >= 40:
                    return {"query": query, "hits": hits}
    return {"query": query, "hits": hits}


def project_context(session: Session, project: Project, max_files: int = 6) -> str:
    """Compact context for the agent: tree highlights, bugs, tests."""
    workspace = workspace_for(project)
    parts = [f"Project: {project.name} ({project.id})", f"Files: {project.file_count}"]
    scan = latest_scan(session, project.id)
    if scan:
        bugs = list(session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all())
        parts.append(f"Latest scan: {scan.id} status={scan.status} findings={len(bugs)}")
        for bug in bugs[:12]:
            parts.append(
                f"- bug {bug.id}: {bug.title} @ {bug.file}:{bug.line} "
                f"[{bug.severity} {bug.confidence:.0%}] {bug.root_cause[:160]}"
            )
    important = json.loads(project.important_json or "[]")
    paths = [item.get("path") for item in important if item.get("path")]
    if not paths:
        paths = [p.relative_to(workspace).as_posix() for p in workspace.rglob("*.py") if p.is_file()][:max_files]
    for rel in paths[:max_files]:
        if not rel or redact_path_name(rel):
            continue
        path = _safe_path(workspace, rel)
        if path is None:
            continue
        try:
            body = redact_text(path.read_text(encoding="utf-8"))[:4000]
        except (OSError, UnicodeDecodeError):
            continue
        parts.append(f"\n----- {rel} -----\n{body}")
    run = session.scalar(select(TestRun).where(TestRun.project_id == project.id).order_by(TestRun.created_at.desc()))
    if run:
        summary = json.loads(run.summary_json or "{}")
        parts.append(
            f"Latest tests: status={run.status} regression={summary.get('regression_passed')} "
            f"generated={summary.get('generated_passed')}"
        )
    return "\n".join(parts)
