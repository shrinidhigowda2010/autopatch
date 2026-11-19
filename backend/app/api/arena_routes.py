"""Break-It attacks, the AI Debate Room, and the Live Repair Race."""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.arena.attack import run_attack
from app.arena.context import latest_test_evidence, patch_context
from app.arena.debate import run_debate
from app.arena.race import run_race
from app.auth import get_optional_user
from app.db import SessionLocal, get_session
from app.ingest.files import IngestError
from app.limiter import limit_request
from app.models import Bug, Patch, Project, User
from app.services import record, user_can_access

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["arena"])
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


class DebateIn(BaseModel):
    attack: dict | None = None


class RaceIn(BaseModel):
    code: str = Field(min_length=1, max_length=200_000)
    filename: str = Field(default="", max_length=120)


def _patch(session: Session, patch_id: str, user: User | None) -> Patch:
    patch = session.get(Patch, patch_id)
    if patch is None:
        raise HTTPException(404, "Patch not found.")
    project = session.get(Project, patch.project_id)
    if project is None or not user_can_access(project, user):
        raise HTTPException(403, "You do not have access to this patch.")
    return patch


def stream(work: Callable[[Session], Iterator[dict]]) -> StreamingResponse:
    """Run a generator in a worker thread with its own DB session and send each event as SSE."""
    out: queue.Queue = queue.Queue()

    def worker() -> None:
        db = SessionLocal()
        try:
            for event in work(db):
                out.put(event)
        except IngestError as exc:
            out.put({"type": "error", "detail": str(exc)})
        except Exception:  # noqa: BLE001
            log.exception("arena stream failed")
            out.put({"type": "error", "detail": "Something went wrong. Try again in a moment."})
        finally:
            db.close()
            out.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def events() -> Iterator[str]:
        while True:
            item = out.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/patches/{patch_id}/attack", dependencies=[Depends(limit_request)])
def attack(patch_id: str, session: Session = Depends(get_session), user: OptionalUser = None) -> dict:
    patch = _patch(session, patch_id, user)
    try:
        result = run_attack(patch_context(session, patch))
    except IngestError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    record(session, patch.project_id, "attack", f"Break-It on {result['function']}: {result['headline']}", bug_id=patch.bug_id)
    session.commit()
    return result


@router.post("/patches/{patch_id}/debate", dependencies=[Depends(limit_request)])
def debate(
    patch_id: str, body: DebateIn | None = None, session: Session = Depends(get_session), user: OptionalUser = None
):
    _patch(session, patch_id, user)
    attack_summary = (body.attack if body else None) or None

    def work(db: Session) -> Iterator[dict]:
        patch = db.get(Patch, patch_id)
        context = patch_context(db, patch)
        evidence = latest_test_evidence(db, context.bug)
        others = [
            bug.title
            for bug in db.scalars(select(Bug).where(Bug.scan_id == context.bug.scan_id, Bug.id != context.bug.id)).all()
            if bug.category != "style"
        ]
        for event in run_debate(context, evidence, attack_summary, other_bugs=others):
            if event["type"] == "verdict":
                label = "Safe" if event["verdict"] == "safe" else "Needs changes"
                record(db, patch.project_id, "debate", f"Debate verdict: {label} ({event['confidence']}%).", bug_id=patch.bug_id)
                db.commit()
            yield event
        yield {"type": "done"}

    return stream(work)


@router.post("/race", dependencies=[Depends(limit_request)])
def race(body: RaceIn, user: OptionalUser = None):
    if not body.code.strip():
        raise HTTPException(400, "Paste some code to race.")
    user_id = user.id if user else None

    def work(db: Session) -> Iterator[dict]:
        yield from run_race(db, body.code, body.filename, user_id=user_id)
        yield {"type": "done"}

    return stream(work)
