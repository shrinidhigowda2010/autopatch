"""In-memory rate limit for upload and scan requests."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request

from app.config import settings


class RateLimiter:
    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self.hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        now = time.monotonic()
        recent = [stamp for stamp in self.hits[key] if now - stamp < self.window]
        if len(recent) >= self.limit:
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute and try again.")
        recent.append(now)
        self.hits[key] = recent


limiter = RateLimiter(settings.rate_limit_per_minute)


def limit_request(request: Request) -> None:
    host = request.client.host if request.client else "local"
    limiter.check(host)
