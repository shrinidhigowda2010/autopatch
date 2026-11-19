"""Oracle for the SQL injection sample."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


def _load(project_dir: Path):
    spec = importlib.util.spec_from_file_location("auth_oracle", project_dir / "auth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table users (id integer, username text, password text)")
    conn.execute("insert into users values (1, 'ada', 'secret')")
    return conn


def check(project_dir: Path) -> list[str]:
    auth = _load(Path(project_dir))
    failures = []
    try:
        row = auth.login(_db(), "ada", "secret")
        if row is None or row[1] != "ada":
            failures.append("valid login stopped working")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"valid login crashed: {exc}")

    try:
        leaked = auth.login(_db(), "nobody' OR '1'='1", "nope")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"injection probe crashed: {exc}")
    else:
        if leaked is not None:
            failures.append("SQL injection still returned a row")

    text = (Path(project_dir) / "auth.py").read_text(encoding="utf-8")
    if "f\"" in text or "f'" in text:
        if "SELECT" in text and "{username}" in text:
            failures.append("username is still interpolated into the query")
    return failures
