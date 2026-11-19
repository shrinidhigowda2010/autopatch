"""Shared lookups: the code before and after a patch, and the function it touches."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.files import IngestError
from app.models import Bug, Patch, Project, TestRun
from app.patching.fixers import propose_fix
from app.services import source_for, workspace_for


@dataclass
class PatchContext:
    project: Project
    bug: Bug
    patch: Patch
    old_source: str
    new_source: str


@dataclass
class Target:
    name: str  # function name
    class_name: str  # "" for a top-level function
    params: list[str]  # positional parameters, without self
    source: str  # the function's code in the patched file


def patch_context(session: Session, patch: Patch) -> PatchContext:
    """Full file text before and after the patch, whether or not it has been applied yet."""
    bug = session.get(Bug, patch.bug_id)
    project = session.get(Project, patch.project_id)
    if bug is None or project is None:
        raise IngestError("That patch is missing its bug or project.", 404)
    current_path = workspace_for(project) / patch.file
    original_path = source_for(project) / patch.file
    current = current_path.read_text(encoding="utf-8") if current_path.is_file() else ""
    before, after = patch.before_code, patch.after_code

    if before and before in current and before != after:
        return PatchContext(project, bug, patch, current, current.replace(before, after, 1))
    if after and after in current:
        old = current.replace(after, before, 1) if before else current
        return PatchContext(project, bug, patch, old, current)
    original = original_path.read_text(encoding="utf-8") if original_path.is_file() else current
    updated = propose_fix(original, bug.rule_id, bug.symbol, json.loads(bug.extra_json or "{}"))
    if not updated:
        raise IngestError("FixPilot couldn't rebuild the code for this patch.", 409)
    return PatchContext(project, bug, patch, original, updated)


def find_target(source: str, symbol: str, line: int = 0) -> Target | None:
    """The function named by the bug, or else the function around its line."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    candidates: list[tuple[ast.FunctionDef, str]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            candidates.append((node, ""))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("__"):
                    candidates.append((item, node.name))
    name = symbol.split(".")[-1] if symbol else ""
    chosen = next(((fn, cls) for fn, cls in candidates if fn.name == name), None)
    if chosen is None and line:
        chosen = next(
            ((fn, cls) for fn, cls in candidates if fn.lineno <= line <= (fn.end_lineno or fn.lineno)),
            None,
        )
    if chosen is None:
        return None
    fn, cls = chosen
    params = [arg.arg for arg in fn.args.posonlyargs + fn.args.args]
    if cls and params and params[0] in {"self", "cls"}:
        params = params[1:]
    return Target(fn.name, cls, params, ast.get_source_segment(source, fn) or "")


def latest_test_evidence(session: Session, bug: Bug) -> dict:
    """What the most recent test run says about this bug, in a small dict."""
    run = session.scalar(
        select(TestRun).where(TestRun.project_id == bug.project_id).order_by(TestRun.created_at.desc())
    )
    if run is None or not run.summary_json:
        return {"has_run": False}
    summary = json.loads(run.summary_json or "{}")
    mine = [
        item
        for item in summary.get("per_bug", [])
        if item.get("rule_id") == bug.rule_id and item.get("symbol") == bug.symbol and item.get("file") == bug.file
    ]
    return {
        "has_run": True,
        "bug_tests_passed": mine[0].get("passed") if mine else None,
        "generated_passed": summary.get("generated_passed"),
        "regression_passed": summary.get("regression_passed"),
        "generated_failed_before": summary.get("generated_before", {}).get("passed") is False,
    }
