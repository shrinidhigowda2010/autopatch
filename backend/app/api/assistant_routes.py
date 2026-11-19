"""Repairo Assistant: conversations and streaming chat."""

from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from typing import Annotated, Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.redaction import redact_text
from app.agent.runner import run_assistant_turn
from app.auth import get_optional_user
from app.db import SessionLocal, get_session
from app.ids import new_id
from app.limiter import RateLimiter
from app.models import ChatMessage, Conversation, Project, User
from app.services import user_can_access

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

OptionalUser = Annotated[User | None, Depends(get_optional_user)]
chat_limiter = RateLimiter(limit=20, window=60.0)

MAX_MESSAGE_CHARS = 4000
MAX_TITLE_CHARS = 120


class ConversationIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=16)
    title: str = Field(default="New chat", max_length=MAX_TITLE_CHARS)
    language: str = Field(default="en", pattern="^(en|kn|hi)$")


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    language: str | None = Field(default=None, pattern="^(en|kn|hi)$")
    bug_id: str | None = None


def _project(session: Session, project_id: str, user: User | None) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found.")
    if not user_can_access(project, user):
        raise HTTPException(403, "You do not have access to this project.")
    return project


def _conversation(session: Session, conversation_id: str, user: User | None) -> Conversation:
    row = session.get(Conversation, conversation_id)
    if row is None:
        raise HTTPException(404, "Conversation not found.")
    _project(session, row.project_id, user)
    if user is not None and user.role != "admin":
        if row.user_id and row.user_id != user.id:
            raise HTTPException(403, "You do not have access to this conversation.")
    if user is None and row.user_id:
        raise HTTPException(403, "Sign in to open this conversation.")
    return row


def _conv_dict(row: Conversation) -> dict:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "user_id": row.user_id,
        "title": row.title,
        "language": row.language,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _msg_dict(row: ChatMessage) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "content": row.content,
        "tool_steps": json.loads(row.tool_steps_json or "[]"),
        "patches": json.loads(row.patches_json or "[]"),
        "created_at": row.created_at.isoformat(),
    }


@router.get("/conversations")
def list_conversations(
    project_id: str,
    session: Session = Depends(get_session),
    user: OptionalUser = None,
) -> dict:
    _project(session, project_id, user)
    query = select(Conversation).where(Conversation.project_id == project_id)
    if user is None:
        query = query.where(Conversation.user_id.is_(None))
    elif user.role != "admin":
        query = query.where(Conversation.user_id == user.id)
    rows = session.scalars(query.order_by(Conversation.updated_at.desc())).all()
    return {"conversations": [_conv_dict(row) for row in rows]}


@router.post("/conversations")
def create_conversation(
    body: ConversationIn,
    session: Session = Depends(get_session),
    user: OptionalUser = None,
) -> dict:
    _project(session, body.project_id, user)
    row = Conversation(
        id=new_id(),
        project_id=body.project_id,
        user_id=user.id if user else None,
        title=(body.title or "New chat")[:MAX_TITLE_CHARS],
        language=body.language,
    )
    session.add(row)
    session.commit()
    return _conv_dict(row)


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
    user: OptionalUser = None,
) -> dict:
    row = _conversation(session, conversation_id, user)
    messages = session.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == row.id).order_by(ChatMessage.created_at)
    ).all()
    return {**_conv_dict(row), "messages": [_msg_dict(msg) for msg in messages]}


@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    body: RenameIn,
    session: Session = Depends(get_session),
    user: OptionalUser = None,
) -> dict:
    row = _conversation(session, conversation_id, user)
    row.title = body.title.strip()[:MAX_TITLE_CHARS]
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    return _conv_dict(row)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
    user: OptionalUser = None,
) -> dict:
    row = _conversation(session, conversation_id, user)
    session.delete(row)
    session.commit()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/messages")
def post_message(
    conversation_id: str,
    body: MessageIn,
    request: Request,
    session: Session = Depends(get_session),
    user: OptionalUser = None,
):
    row = _conversation(session, conversation_id, user)
    project = _project(session, row.project_id, user)
    host = request.client.host if request.client else "local"
    key = f"chat:{(user.id if user else host)}:{row.project_id}"
    chat_limiter.check(key)

    content = redact_text(body.content.strip())
    if body.bug_id:
        content = f"[Context: bug_id={body.bug_id}]\n{content}"
    if body.language:
        row.language = body.language

    user_msg = ChatMessage(
        id=new_id(),
        conversation_id=row.id,
        role="user",
        content=content,
    )
    session.add(user_msg)
    session.commit()

    prior = session.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == row.id, ChatMessage.id != user_msg.id)
        .order_by(ChatMessage.created_at)
    ).all()
    history = [{"role": msg.role, "content": msg.content} for msg in prior if msg.role in {"user", "assistant"}]

    conversation_id_value = row.id
    project_id_value = project.id
    language = row.language
    user_content = content
    user_message_id = user_msg.id

    def event_stream() -> Iterator[str]:
        out: queue.Queue = queue.Queue()

        def worker() -> None:
            db = SessionLocal()
            try:
                conv = db.get(Conversation, conversation_id_value)
                proj = db.get(Project, project_id_value)
                if conv is None or proj is None:
                    out.put({"type": "error", "detail": "Conversation missing."})
                    return

                def emit(event: dict) -> None:
                    out.put(event)

                out.put({"type": "start", "user_message_id": user_message_id})
                result = run_assistant_turn(
                    db,
                    proj,
                    history,
                    user_content,
                    language=language,
                    emit=emit,
                )
                assistant = ChatMessage(
                    id=new_id(),
                    conversation_id=conv.id,
                    role="assistant",
                    content=result["content"],
                    tool_steps_json=json.dumps(result.get("tool_steps") or []),
                    patches_json=json.dumps(result.get("patches") or []),
                )
                conv.updated_at = datetime.now(timezone.utc)
                if conv.title == "New chat":
                    conv.title = user_content[:60] + ("…" if len(user_content) > 60 else "")
                db.add(assistant)
                db.commit()
                out.put({"type": "saved", "message": _msg_dict(assistant)})
            except Exception as exc:  # noqa: BLE001
                out.put({"type": "error", "detail": str(exc)})
            finally:
                db.close()
                out.put(None)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            item = out.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
