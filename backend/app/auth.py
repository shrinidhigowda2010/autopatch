"""Password hashing, JWT tokens, and FastAPI auth dependencies."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.limiter import RateLimiter
from app.models import User

# Cost 10 keeps sign-in under half a second on a laptop; older cost-12 hashes still verify.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=10)
bearer_scheme = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"
ACCESS_TOKEN_HOURS = 24

# Stricter than the general API limiter: 10 login attempts per minute per key.
login_limiter = RateLimiter(limit=10, window=60.0)

_CODER_ALPHABET = string.ascii_uppercase + string.digits
CODER_PREFIX = "FP-CODER-"
LEGACY_CODER_PREFIX = "AP-CODER-"


def coder_id_candidates(identifier: str) -> list[str]:
    """IDs to look up for a typed coder ID. Old AP-CODER IDs and new FP-CODER IDs both work."""
    value = identifier.strip().upper()
    for prefix, other in ((CODER_PREFIX, LEGACY_CODER_PREFIX), (LEGACY_CODER_PREFIX, CODER_PREFIX)):
        if value.startswith(prefix):
            return [value, other + value[len(prefix):]]
    return [value]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, password_hash: str) -> bool:
    return pwd_context.verify(plain, password_hash)


def generate_coder_id(session: Session) -> str:
    for _ in range(32):
        suffix = "".join(secrets.choice(_CODER_ALPHABET) for _ in range(5))
        coder_id = f"{CODER_PREFIX}{suffix}"
        exists = session.scalar(select(User.id).where(User.coder_id == coder_id))
        if not exists:
            return coder_id
    raise RuntimeError("Could not allocate a unique coder ID.")


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_HOURS)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again.",
        ) from exc
    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    return user_id


def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User | None:
    if credentials is None:
        return None
    user_id = decode_token(credentials.credentials)
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def require_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Log in or continue as guest.",
        )
    return user


def check_login_rate(request: Request, identifier: str) -> None:
    host = request.client.host if request.client else "local"
    login_limiter.check(f"login:{host}:{identifier.lower()}")
