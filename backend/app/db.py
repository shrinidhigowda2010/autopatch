"""SQLAlchemy session setup. SQLite by default, Postgres when DATABASE_URL is set."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.resolved_database_url
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _connection_record):  # noqa: ANN001
        if url.startswith("sqlite"):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# create_all will not ALTER existing tables. Add new columns for upgrades.
_SQLITE_COLUMN_MIGRATIONS = {
    "chat_messages": [
        ("feedback", "INTEGER"),
    ],
    "projects": [
        ("user_id", "VARCHAR(16)"),
        ("is_guest", "BOOLEAN DEFAULT 0"),
    ],
    "scans": [
        ("user_id", "VARCHAR(16)"),
    ],
    "patches": [
        ("user_id", "VARCHAR(16)"),
    ],
    "decisions": [
        ("user_id", "VARCHAR(16)"),
    ],
}


def _migrate_sqlite() -> None:
    if not settings.resolved_database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        for table, columns in _SQLITE_COLUMN_MIGRATIONS.items():
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            if not existing:
                continue  # table will be created by create_all
            for name, col_type in columns:
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
                log.info("added column %s.%s", table, name)


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
