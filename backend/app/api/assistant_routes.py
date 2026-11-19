"""FixPilot Assistant: conversations and streaming chat."""

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
from app.agent.snippets import extract_code
from app.auth import get_optional_user
from app.db import SessionLocal, get_session
from app.ids import new_id
from app.limiter import RateLimiter
from app.models import ChatMessage, Conversation, Project, User
from app.ingest.files import IngestError
from app.services import SCRATCH_SOURCE, create_scratch_project, replace_scratch_files, user_can_access

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

OptionalUser = Annotated[User | None, Depends(get_optional_user)]
chat_limiter = RateLimiter(limit=20, window=60.0)

MAX_MESSAGE_CHARS = 12000  # room for an attached file
MAX_TITLE_CHARS = 120


class ConversationIn(BaseModel):
    project_id: str | None = Field(default=None, max_length=16)  # empty: a standalone chat
    title: str = Field(default="New chat", max_length=MAX_TITLE_CHARS)
    language: str = Field(default="en", pattern="^(en|kn|hi)$")


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    language: str | None = Field(default=None, pattern="^(en|kn|hi)$")
    bug_id: str | None = None
    mode: str = Field(default="auto", pattern="^(auto|explain|fix|review)$")


class FeedbackIn(BaseModel):
    value: int = Field(ge=-1, le=1)  # 1 helpful, -1 not helpful, 0 clears




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


def _conv_dict(row: Conversation, project: Project | None = None) -> dict:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "standalone": bool(project and project.source_type == SCRATCH_SOURCE),
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
        "feedback": row.feedback,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/conversations")
def list_conversations(
    project_id: str | None = None,
    ids: str = "",
    session: Session = Depends(get_session),
    user: OptionalUser = None,
) -> dict:
    """Chats for one project, or (no project_id) the user's standalone chats.

    Guests have no account to list by, so the browser passes the ids of the chats it started.
    """
    if project_id:
        _project(session, project_id, user)
        query = select(Conversation).where(Conversation.project_id == project_id)
    else:
        query = select(Conversation).join(Project, Project.id == Conversation.project_id)
        query = query.where(Project.source_type == SCRATCH_SOURCE)
        if user is None:
            wanted = [item for item in ids.split(",") if item][:100]
            query = query.where(Conversation.id.in_(wanted))
    if user is None:
        query = query.where(Conversation.user_id.is_(None))
    elif user.role != "admin":
        query = query.where(Conversation.user_id == user.id)
    rows = session.scalars(query.order_by(Conversation.updated_at.desc()).limit(200)).all()
    return {"conversations": [_conv_dict(row, session.get(Project, row.project_id)) for row in rows]}


@router.post("/conversations")
def create_conversation(
    body: ConversationIn,
    session: Session = Depends(get_session),
    user: OptionalUser = None,
) -> dict:
    if body.project_id:
        project = _project(session, body.project_id, user)
    else:
        project = create_scratch_project(session, user)
    row = Conversation(
        id=new_id(),
        project_id=project.id,
        user_id=user.id if user else None,
        title=(body.title or "New chat")[:MAX_TITLE_CHARS],
        language=body.language,
    )
    session.add(row)
    session.commit()
    return _conv_dict(row, project)


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
    user: OptionalUser = None,
) -> dict:
    row = _conversation(session, conversation_id, user)
    project = session.get(Project, row.project_id)
    messages = session.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == row.id).order_by(ChatMessage.created_at)
    ).all()
    return {
        **_conv_dict(row, project),
        "project_name": project.name if project else "",
        "file_count": project.file_count if project else 0,
        "messages": [_msg_dict(msg) for msg in messages],
    }


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

    # In a standalone chat, code pasted into the message becomes the chat's project.
    code_changed = False
    if project.source_type == SCRATCH_SOURCE:
        files = extract_code(body.content)
        if files:
            try:
                replace_scratch_files(session, project, files)
                code_changed = True
            except IngestError as exc:
                raise HTTPException(400, str(exc)) from exc

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
    mode = body.mode
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
                    mode=mode,
                    code_changed=code_changed,
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


@router.post("/messages/{message_id}/feedback")
def message_feedback(
    message_id: str,
    body: FeedbackIn,
    session: Session = Depends(get_session),
    user: OptionalUser = None,
) -> dict:
    row = session.get(ChatMessage, message_id)
    if row is None or row.role != "assistant":
        raise HTTPException(404, "Reply not found.")
    _conversation(session, row.conversation_id, user)
    row.feedback = body.value or None
    session.commit()
    return {"id": row.id, "feedback": row.feedback}
