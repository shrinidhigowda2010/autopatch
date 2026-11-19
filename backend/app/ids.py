"""Short ids for rows. 12 hex chars is enough for a hackathon database."""

from __future__ import annotations

import uuid


def new_id() -> str:
    return uuid.uuid4().hex[:12]
