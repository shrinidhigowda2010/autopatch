"""Standalone assistant chats, answers built from the scan, and the Gemini tool loop."""

from __future__ import annotations

import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.agent import runner
from app.agent.snippets import extract_code
from app.db import SessionLocal, init_db
from app.main import app
from app.models import Project

BUGGY = "def average(x): return sum(x)/len(x)"


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


def _events(response) -> list[dict]:
    return [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]


def _reply(events: list[dict]) -> str:
    return "".join(event["text"] for event in events if event["type"] == "token")


def test_extract_code_finds_inline_and_fenced_code():
    assert extract_code(f"Find bugs in: {BUGGY}") == [("snippet.py", BUGGY + "\n")]
    fenced = extract_code("Look:\n```python\n# marks.py\ndef f(a):\n    return a[0]\n```")
    assert fenced == [("marks.py", "def f(a):\n    return a[0]\n")]
    assert extract_code("What is a closure in Python?") == []
    assert extract_code("why does my loop from x import y fail") == []


def test_standalone_chat_without_a_project(client):
    created = client.post("/api/assistant/conversations", json={})
    assert created.status_code == 200, created.text
    conv = created.json()
    assert conv["standalone"] is True

    with mock.patch("app.agent.runner.gemini_usable", return_value=False):
        response = client.post(f"/api/assistant/conversations/{conv['id']}/messages", json={"content": "Hello there"})
    events = _events(response)
    assert any(event["type"] == "saved" for event in events)
    assert "Paste the code" in _reply(events)

    # Guests list standalone chats by the ids their browser remembers.
    listed = client.get(f"/api/assistant/conversations?ids={conv['id']}").json()["conversations"]
    assert [row["id"] for row in listed] == [conv["id"]]
    assert client.get("/api/assistant/conversations?ids=").json()["conversations"] == []

    # The hidden scratch project never shows up as a normal project.
    with SessionLocal() as session:
        assert session.get(Project, conv["project_id"]).source_type == "assistant"


def test_fallback_answer_names_the_real_bug(client):
    conv = client.post("/api/assistant/conversations", json={}).json()
    with mock.patch("app.agent.runner.gemini_usable", return_value=False):
        response = client.post(
            f"/api/assistant/conversations/{conv['id']}/messages",
            json={"content": f"Find bugs in: {BUGGY}"},
        )
    events = _events(response)
    reply = _reply(events)
    assert "division by zero" in reply.lower()
    assert "snippet.py" in reply and "line 1" in reply
    assert "if not x:" in reply  # the suggested patch is shown
    assert any(event["type"] == "patch" for event in events)
    assert not any(word in reply.lower() for word in ("demo", "try: “find all bugs"))

    with mock.patch("app.agent.runner.gemini_usable", return_value=False):
        explained = _reply(_events(client.post(
            f"/api/assistant/conversations/{conv['id']}/messages", json={"content": "Explain it simply"}
        )))
    assert "ZeroDivisionError" in explained


def test_tool_loop_always_ends_with_an_answer(client):
    conv = client.post("/api/assistant/conversations", json={}).json()
    calls: list[bool] = []

    def fake_stream(contents, system, tools, allow_tools, on_text):
        calls.append(allow_tools)
        if allow_tools:  # keeps asking for tools while it is allowed to
            return "", [{"name": "search_code", "args": {"query": "len"}}], [{"functionCall": {"name": "search_code"}}]
        on_text("The bug: average() divides by len(x), so an empty list raises ZeroDivisionError.")
        return "The bug: ...", [], []

    with mock.patch("app.agent.runner.gemini_usable", return_value=True), \
         mock.patch("app.agent.runner.settings") as settings, \
         mock.patch("app.agent.runner._gemini_stream", side_effect=fake_stream):
        settings.gemini_configured = True
        response = client.post(
            f"/api/assistant/conversations/{conv['id']}/messages", json={"content": f"Find bugs in: {BUGGY}"}
        )
    events = _events(response)
    assert calls == [True] * runner.MAX_TOOL_ROUNDS + [False]
    assert "ZeroDivisionError" in _reply(events)
    assert any(event["type"] == "saved" for event in events)


def test_model_failure_falls_back_to_scan_answer(client):
    conv = client.post("/api/assistant/conversations", json={}).json()
    with mock.patch("app.agent.runner.gemini_usable", return_value=True), \
         mock.patch("app.agent.runner.settings") as settings, \
         mock.patch("app.agent.runner._gemini_stream", side_effect=runner.GeminiError("503")):
        settings.gemini_configured = True
        response = client.post(
            f"/api/assistant/conversations/{conv['id']}/messages", json={"content": f"Find bugs in: {BUGGY}"}
        )
    assert "division by zero" in _reply(_events(response)).lower()


def test_account_overview_and_history(client):
    token = client.post(
        "/api/auth/register",
        json={"full_name": "Meera", "email": "meera-overview@example.com", "password": "password123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    project = client.post("/api/projects/sample", json={"sample_id": "marks_calculator"}, headers=headers).json()
    client.post(f"/api/projects/{project['id']}/scans", headers=headers)

    overview = client.get("/api/me/overview", headers=headers).json()
    assert overview["guest"] is False
    assert overview["totals"]["projects"] == 1 and overview["totals"]["scans"] == 1
    assert overview["totals"]["bugs_found"] >= 1
    assert overview["projects"][0]["id"] == project["id"]
    assert overview["trend"]

    history = client.get("/api/me/history", headers=headers).json()
    assert any(event["kind"] == "scan_finished" for event in history["events"])

    # Guests only see projects their browser passes in, never other people's.
    guest_project = client.post("/api/projects/sample", json={"sample_id": "div_zero"}).json()
    guest = client.get(f"/api/me/overview?ids={guest_project['id']},{project['id']}").json()
    assert guest["guest"] is True
    assert [row["id"] for row in guest["projects"]] == [guest_project["id"]]
    assert client.get("/api/me/history").json()["events"] == []
