"""Runtime settings. Environment variables override the defaults."""

from __future__ import annotations

import os
from pathlib import Path

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
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-2.0-flash"
    gemini_timeout_s: float = 25.0
    gemini_retries: int = 2

    database_url: str = ""
    max_upload_mb: int = 8
    max_files: int = 400
    max_unzip_mb: int = 32

    sandbox_timeout_s: int = 20
    sandbox_mem_mb: int = 512
    rate_limit_per_minute: int = 40
    app_env: str = "development"
    jwt_secret: str = "dev-only-change-me-autopatch-jwt-secret"

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def samples_dir(self) -> Path:
        return REPO_ROOT / "samples"

    @property
    def data_dir(self) -> Path:
        raw = os.environ.get("AUTOPATCH_DATA_DIR", "").strip()
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
