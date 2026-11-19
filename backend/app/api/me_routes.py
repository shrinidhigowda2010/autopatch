"""Account-level views: every project, scan and decision that belongs to the caller.

Signed-in users see their own projects. Guests have no account, so the browser
sends the ids of projects it opened in this session.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_optional_user
from app.db import get_session
from app.models import Bug, Decision, HistoryEvent, Project, Scan, User
from app.services import SCRATCH_SOURCE, health_score

router = APIRouter(prefix="/api/me", tags=["me"])

OptionalUser = Annotated[User | None, Depends(get_optional_user)]

APPROVED = {"approved", "auto-applied", "edited"}


def _my_projects(session: Session, user: User | None, ids: str) -> list[Project]:
    query = select(Project).where(Project.source_type != SCRATCH_SOURCE)
    if user is None:
        wanted = [item for item in ids.split(",") if item][:100]
        if not wanted:
            return []
        query = query.where(Project.id.in_(wanted), Project.user_id.is_(None))
    elif user.role != "admin":
        query = query.where(Project.user_id == user.id)
    return list(session.scalars(query.order_by(Project.created_at.desc()).limit(200)).all())


@router.get("/overview")
def overview(ids: str = "", session: Session = Depends(get_session), user: OptionalUser = None) -> dict:
    projects = _my_projects(session, user, ids)
    by_id = {project.id: project for project in projects}
    scans = (
        list(session.scalars(select(Scan).where(Scan.project_id.in_(by_id)).order_by(Scan.started_at)).all())
        if by_id
        else []
    )
    bugs_per_scan: dict[str, int] = dict(
        session.execute(
            select(Bug.scan_id, func.count())
            .where(Bug.project_id.in_(by_id), Bug.category != "style")
            .group_by(Bug.scan_id)
        ).all()
    ) if by_id else {}
    decisions: dict[str, int] = dict(
        session.execute(
            select(Decision.action, func.count()).where(Decision.project_id.in_(by_id)).group_by(Decision.action)
        ).all()
    ) if by_id else {}

    latest: dict[str, Scan] = {}
    scan_count: dict[str, int] = {}
    for scan in scans:
        latest[scan.project_id] = scan
        scan_count[scan.project_id] = scan_count.get(scan.project_id, 0) + 1

    health: dict[str, dict] = {pid: health_score(session, by_id[pid], scan) for pid, scan in latest.items()}
    trend = []
    for scan in [item for item in scans if item.status == "complete"][-20:]:
        score = health[scan.project_id] if latest[scan.project_id] is scan else health_score(session, by_id[scan.project_id], scan)
        trend.append(
            {
                "at": scan.started_at.isoformat(),
                "project": by_id[scan.project_id].name,
                "before": score["before"],
                "after": score["after"],
            }
        )

    rows: list[dict[str, Any]] = []
    for project in projects:
        last = latest.get(project.id)
        rows.append(
            {
                "id": project.id,
                "name": project.name,
                "source_type": project.source_type,
                "created_at": project.created_at.isoformat(),
                "scans": scan_count.get(project.id, 0),
                "bugs": bugs_per_scan.get(last.id, 0) if last else 0,
                "health": health[project.id]["after"] if last else None,
                "last_scan_at": last.started_at.isoformat() if last else None,
            }
        )
    scored = [row["health"] for row in rows if row["health"] is not None]
    return {
        "guest": user is None,
        "totals": {
            "projects": len(projects),
            "scans": len(scans),
            "bugs_found": sum(bugs_per_scan.get(scan.id, 0) for scan in latest.values()),
            "fixes_approved": sum(count for action, count in decisions.items() if action in APPROVED),
            "fixes_rejected": decisions.get("rejected", 0),
            "avg_health": round(sum(scored) / len(scored)) if scored else None,
        },
        "trend": trend,
        "projects": rows,
    }


@router.get("/history")
def history(ids: str = "", session: Session = Depends(get_session), user: OptionalUser = None) -> dict:
    projects = _my_projects(session, user, ids)
    names = {project.id: project.name for project in projects}
    events = (
        session.scalars(
            select(HistoryEvent).where(HistoryEvent.project_id.in_(names)).order_by(HistoryEvent.id.desc()).limit(300)
        ).all()
        if names
        else []
    )
    return {
        "guest": user is None,
        "projects": [
            {"id": project.id, "name": project.name, "source_type": project.source_type, "created_at": project.created_at.isoformat()}
            for project in projects
        ],
        "events": [
            {
                "project_id": event.project_id,
                "project_name": names.get(event.project_id, ""),
                "kind": event.kind,
                "message": event.message,
                "bug_id": event.bug_id,
                "at": event.created_at.isoformat(),
            }
            for event in events
        ],
    }
