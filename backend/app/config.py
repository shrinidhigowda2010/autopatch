"""Runtime settings. Environment variables override the defaults."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Values read from the environment or a `.env` file at the repo root."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.1-flash-lite"
    # A full-project scan prompt takes Gemini 20-35 s when it is busy; quick calls pass their own shorter timeout.
    gemini_timeout_s: float = 45.0
    gemini_retries: int = 2

    database_url: str = ""
    max_upload_mb: int = 8
    max_files: int = 400
    max_unzip_mb: int = 32

    sandbox_timeout_s: int = 20
    sandbox_mem_mb: int = 512
    rate_limit_per_minute: int = 40
    app_env: str = "development"
    jwt_secret: str = "dev-only-change-me-fixpilot-jwt-secret"

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def _clean_key(cls, value: object) -> str:
        """Forgive the usual copy-paste slips: spaces, new lines, quotes, or the whole `NAME=value` line."""
        key = str(value or "").strip()
        if key.upper().startswith("GEMINI_API_KEY="):
            key = key.split("=", 1)[1].strip()
        return key.strip("\"'` ").strip()

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def samples_dir(self) -> Path:
        return REPO_ROOT / "samples"

    @property
    def data_dir(self) -> Path:
        # FIXPILOT_DATA_DIR is the new name; AUTOPATCH_DATA_DIR still works for older setups.
        raw = (os.environ.get("FIXPILOT_DATA_DIR") or os.environ.get("AUTOPATCH_DATA_DIR", "")).strip()
        path = Path(raw) if raw else REPO_ROOT / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resolved_database_url(self) -> str:
        url = (self.database_url or os.environ.get("DATABASE_URL", "")).strip()
        if not url:
            db_file = self.data_dir / "autopatch.db"
            return f"sqlite:///{db_file}"
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://") and "+psycopg" not in url:
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key.strip())


settings = Settings()
