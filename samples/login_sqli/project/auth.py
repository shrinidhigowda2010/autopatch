"""Login helper. The database compares the password."""

import sqlite3


def login(conn, username, password):
    """Return the user row, or None when the password does not match."""
    query = f"SELECT id, username FROM users WHERE username = '{username}' AND password = '{password}'"
    row = conn.execute(query).fetchone()
    return row


def connect(path):
    """Open a sqlite database file."""
    return sqlite3.connect(path)
