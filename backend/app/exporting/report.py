"""JSON, PDF and zip exports of a reviewed project."""

from __future__ import annotations

import io
import json
import zipfile  # noqa: F401 — used below via ZipFile, keep import explicit
from pathlib import Path

from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bug, Patch, Project, Scan, TestRun
from app.services import decision_log, workspace_for


def report_payload(session: Session, project: Project, scan: Scan | None) -> dict:
    bugs = []
    if scan:
        rows = session.scalars(select(Bug).where(Bug.scan_id == scan.id)).all()
        for bug in rows:
            patch = session.scalar(select(Patch).where(Patch.bug_id == bug.id).order_by(Patch.created_at.desc()))
            bugs.append(
                {
                    "bug_details": {
                        "id": bug.id,
                        "file": bug.file,
                        "line": bug.line,
                        "symbol": bug.symbol,
                        "title": bug.title,
                        "description": bug.description,
                        "category": bug.category,
                        "snippet": bug.snippet,
                        "source": bug.source,
                    },
                    "root_cause": {
                        "root_cause": bug.root_cause,
                        "trigger": bug.trigger,
                        "student_explanation": bug.student_explanation,
                    },
                    "suggested_patch": None
                    if patch is None
                    else {
                        "id": patch.id,
                        "status": patch.status,
                        "diff": patch.diff,
                        "before": patch.before_code,
                        "after": patch.after_code,
                    },
                    "severity_and_confidence": {
                        "severity": bug.severity,
                        "confidence": bug.confidence,
                        "impact": bug.impact,
                        "needs_human_review": bug.needs_human_review,
                    },
                }
            )
    runs = session.scalars(select(TestRun).where(TestRun.project_id == project.id)).all()
    decisions = decision_log(session, project.id)
    return {
        "project": {"id": project.id, "name": project.name, "source_type": project.source_type},
        "scan": None if scan is None else {"id": scan.id, "mode": scan.mode, "status": scan.status},
        "bugs": bugs,
        "test_runs": [
            {"id": run.id, "status": run.status, "summary": json.loads(run.summary_json or "{}")} for run in runs
        ],
        "decision_log": decisions,
    }


def render_pdf(payload: dict) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    def write(text: str, size: int = 10, bold: bool = False, height: int = 6, font: str = "Helvetica") -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(font, "B" if bold else "", size)
        pdf.multi_cell(pdf.epw, height, _latin(text))

    write(f"FixPilot report: {payload['project']['name']}", size=16, bold=True, height=10)
    scan = payload.get("scan") or {}
    write(f"Scan {scan.get('id', 'n/a')} / mode {scan.get('mode', 'n/a')}", size=11, height=7)
    for bug in payload["bugs"]:
        details = bug["bug_details"]
        severity = bug["severity_and_confidence"]
        write(details["title"], size=12, bold=True, height=7)
        write(
            f"Bug details: {details['file']}:{details['line']} {details['symbol']} "
            f"[{severity['severity']}, confidence {severity['confidence']:.0%}]"
        )
        cause = bug["root_cause"]
        write(f"Root cause: {cause['root_cause']}")
        write(f"Trigger: {cause['trigger']}")
        patch = bug["suggested_patch"]
        if patch:
            write(f"Suggested patch status: {patch['status']}")
            write(patch["diff"][:1800], size=8, height=4, font="Courier")
        pdf.ln(2)
    decisions = payload.get("decision_log") or []
    if decisions:
        write("Decision log", size=13, bold=True, height=8)
        for item in decisions:
            write(
                f"{item.get('timestamp', '')} · {item.get('decision', '')} · "
                f"{item.get('who', 'Guest')} · fix {item.get('fix_id', '')}"
                + (f" · {item['note']}" if item.get("note") else ""),
                size=9,
                height=5,
            )
    return bytes(pdf.output())


def zip_workspace(project: Project) -> bytes:
    root = workspace_for(project)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(root).as_posix())
        archive.writestr(
            "FIXPILOT.txt",
            "This zip is the workspace after any patches you accepted.\n"
            "Files you rejected are unchanged.\n",
        )
    return buffer.getvalue()


def _latin(text: str) -> str:
    raw = text or ""
    pieces = []
    for chunk in raw.splitlines() or [""]:
        folded = chunk
        while len(folded) > 90:
            pieces.append(folded[:90])
            folded = folded[90:]
        pieces.append(folded)
    cleaned = "\n".join(ch if 32 <= ord(ch) < 127 else " " for ch in "\n".join(pieces))
    return cleaned.strip() or "-"
