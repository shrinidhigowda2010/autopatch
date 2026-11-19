"""Fixpilot web service. The API and, when built, the React app live here."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app import __version__
from app.api.assistant_routes import router as assistant_router
from app.api.auth_routes import router as auth_router
from app.api.routes import router
from app.config import settings
from app.db import init_db
from app.ingest.files import IngestError
from app.logging_config import setup_logging

log = logging.getLogger(__name__)
DIST = settings.repo_root / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    init_db()
    log.info("fixpilot ready")
    yield


app = FastAPI(
    title="Fixpilot",
    version=__version__,
    summary="Find it. Fix it. Prove it.",
    lifespan=lifespan,
)
app.include_router(auth_router)
app.include_router(assistant_router)
app.include_router(router)


@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error", extra={"method": request.method, "path": request.url.path})
        raise
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    logging.getLogger("autopatch.access").info(
        "request",
        extra={"method": request.method, "path": request.url.path, "status": response.status_code, "ms": elapsed},
    )
    return response


@app.exception_handler(IngestError)
async def ingest_error(_request: Request, exc: IngestError):
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unexpected(_request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    log.exception("request failed")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong while handling that request."})


def _dist_file(full_path: str) -> Path | None:
    if not DIST.is_dir():
        return None
    candidate = (DIST / full_path).resolve()
    if str(candidate).startswith(str(DIST.resolve())) and candidate.is_file():
        return candidate
    return None


def _spa_index() -> Path | None:
    index = DIST / "index.html"
    return index if index.is_file() else None


def _file_response(path: Path, *, cache: bool) -> FileResponse:
    headers = {}
    if not cache:
        # Always revalidate the shell so rebuilds do not leave a blank page
        # pointing at deleted hashed assets.
        headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    else:
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return FileResponse(path, headers=headers)


@app.get("/", include_in_schema=False)
def home():
    page = _spa_index()
    if page:
        return _file_response(page, cache=False)
    return {"name": "Fixpilot", "docs": "/docs", "health": "/api/health"}


@app.get("/{full_path:path}", include_in_schema=False)
def frontend(full_path: str):
    if full_path.startswith("api"):
        raise HTTPException(404, "Not found.")
    page = _dist_file(full_path)
    if page is not None:
        # Hashed build assets can be cached; everything else revalidates.
        is_asset = full_path.startswith("assets/")
        return _file_response(page, cache=is_asset)
    # Missing hashed assets must 404 (not return index.html), or the browser
    # tries to execute HTML as a module and the app stays blank.
    name = Path(full_path).name
    if "." in name and not name.endswith(".html"):
        raise HTTPException(404, "Not found.")
    index = _spa_index()
    if index is None:
        raise HTTPException(404, "Frontend is not built. Run the API docs at /docs.")
    return _file_response(index, cache=False)
