"""Persistence boundary for scans, bugs, patches, tests and decisions.

The tables live in :mod:`app.models`. SQLite is the default file database.
Set ``DATABASE_URL`` to a Postgres URL when deploying. Routes take a session
from :func:`app.db.get_session` and never write a patch until a person accepts
it, or until "apply all safe fixes" clears the confidence and test gates.
"""

from app.db import SessionLocal, get_session, init_db

__all__ = ["SessionLocal", "get_session", "init_db"]
