"""A valid user can still log in. This does not try an injection."""

import sqlite3

from auth import login


def test_valid_user():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table users (id integer, username text, password text)")
    conn.execute("insert into users values (1, 'ada', 'secret')")
    row = login(conn, "ada", "secret")
    assert row is not None
    assert row[1] == "ada"
