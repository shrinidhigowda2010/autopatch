"""Authentication: register, login, me, logout, profile stats."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    check_login_rate,
    create_access_token,
    coder_id_candidates,
    generate_coder_id,
    hash_password,
    require_user,
    verify_password,
)
from app.db import get_session
from app.ids import new_id
from app.models import Project, User
from app.services import SCRATCH_SOURCE, profile_stats

router = APIRouter(prefix="/api/auth", tags=["auth"])

ALLOWED_ROLES = {"student", "developer", "admin"}


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="student")


class LoginIn(BaseModel):
    # Email or coder_id
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


def _user_public(user: User, session: Session | None = None) -> dict:
    payload = {
        "id": user.id,
        "coder_id": user.coder_id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }
    if session is not None:
        payload["stats"] = profile_stats(session, user)
    return payload


@router.post("/register")
def register(body: RegisterIn, session: Session = Depends(get_session)) -> dict:
    role = (body.role or "student").lower().strip()
    if role not in ALLOWED_ROLES:
        raise HTTPException(400, "Role must be student, developer, or admin.")
    email = body.email.lower().strip()
    existing = session.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(400, "An account with that email already exists.")
    user = User(
        id=new_id(),
        coder_id=generate_coder_id(session),
        full_name=body.full_name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        role=role,
    )
    session.add(user)
    session.commit()
    token = create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "coder_id": user.coder_id,
        "user": _user_public(user, session),
        "message": f"Welcome! Your Coder ID is {user.coder_id}",
    }


@router.post("/login")
def login(body: LoginIn, request: Request, session: Session = Depends(get_session)) -> dict:
    identifier = body.identifier.strip()
    check_login_rate(request, identifier)
    user = session.scalar(select(User).where(User.email == identifier.lower()))
    if user is None:
        user = session.scalar(select(User).where(User.coder_id.in_(coder_id_candidates(identifier))))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/Coder ID or password.",
        )
    user.last_login = datetime.now(timezone.utc)
    session.commit()
    token = create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "coder_id": user.coder_id,
        "user": _user_public(user, session),
    }


@router.get("/me")
def me(user: User = Depends(require_user), session: Session = Depends(get_session)) -> dict:
    return _user_public(user, session)


@router.post("/logout")
def logout(user: User = Depends(require_user)) -> dict:
    # JWT is stateless; client discards the token. Endpoint exists for a clean UX + audit.
    return {"ok": True, "message": "Logged out. Discard your access token."}


@router.get("/history")
def my_history(user: User = Depends(require_user), session: Session = Depends(get_session)) -> dict:
    if user.role == "admin":
        rows = session.scalars(
            select(Project).where(Project.source_type != SCRATCH_SOURCE).order_by(Project.created_at.desc()).limit(100)
        ).all()
    else:
        rows = session.scalars(
            select(Project)
            .where(Project.user_id == user.id, Project.source_type != SCRATCH_SOURCE)
            .order_by(Project.created_at.desc())
        ).all()
    return {
        "projects": [
            {
                "id": row.id,
                "name": row.name,
                "source_type": row.source_type,
                "created_at": row.created_at.isoformat(),
                "is_guest": row.is_guest,
            }
            for row in rows
        ],
        "stats": profile_stats(session, user),
    }
