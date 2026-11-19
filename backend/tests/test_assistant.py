"""Repairo Assistant: conversations, isolation, tools, redaction."""

from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.agent.redaction import redact_path_name, redact_text
from app.agent.tools import execute_tool
from app.db import SessionLocal, init_db
from app.main import app
from app.models import Project


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


def _register(client: TestClient, email: str, name: str = "User"):
    return client.post(
        "/api/auth/register",
        json={"full_name": name, "email": email, "password": "password123", "role": "student"},
    )


def _project_for(client: TestClient, token: str | None = None) -> str:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    created = client.post("/api/projects/sample", json={"sample_id": "marks_calculator"}, headers=headers)
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_create_conversation(client):
    project_id = _project_for(client)
    created = client.post(
        "/api/assistant/conversations",
        json={"project_id": project_id, "title": "Marks help", "language": "en"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["project_id"] == project_id
    assert body["title"] == "Marks help"
    listed = client.get(f"/api/assistant/conversations?project_id={project_id}")
    assert listed.status_code == 200
    assert any(row["id"] == body["id"] for row in listed.json()["conversations"])


def test_send_message_streams_and_saves(client):
    project_id = _project_for(client)
    client.post(f"/api/projects/{project_id}/scans")
    conv = client.post(
        "/api/assistant/conversations",
        json={"project_id": project_id, "title": "New chat"},
    ).json()

    with mock.patch("app.agent.runner.settings") as settings:
        settings.gemini_configured = False
        response = client.post(
            f"/api/assistant/conversations/{conv['id']}/messages",
            json={"content": "Find all bugs in this project", "language": "en"},
        )
    assert response.status_code == 200, response.text
    assert "text/event-stream" in response.headers.get("content-type", "")
    payload = response.text
    assert "data:" in payload
    assert '"type": "start"' in payload or '"type":"start"' in payload.replace(" ", "")
    # Saved message should appear in history
    detail = client.get(f"/api/assistant/conversations/{conv['id']}")
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert any(msg["role"] == "user" for msg in messages)
    assert any(msg["role"] == "assistant" for msg in messages)


def test_history_isolation_between_users(client):
    a = _register(client, "assist-a@example.com", "A")
    b = _register(client, "assist-b@example.com", "B")
    token_a = a.json()["access_token"]
    token_b = b.json()["access_token"]
    project_a = _project_for(client, token_a)
    project_b = _project_for(client, token_b)

    conv_a = client.post(
        "/api/assistant/conversations",
        json={"project_id": project_a, "title": "A private"},
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()
    conv_b = client.post(
        "/api/assistant/conversations",
        json={"project_id": project_b, "title": "B private"},
        headers={"Authorization": f"Bearer {token_b}"},
    ).json()

    list_a = client.get(
        f"/api/assistant/conversations?project_id={project_a}",
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()["conversations"]
    assert any(row["id"] == conv_a["id"] for row in list_a)

    denied = client.get(
        f"/api/assistant/conversations/{conv_a['id']}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert denied.status_code in {403, 404}

    # B should not see A's conversation on A's project either
    cross = client.get(
        f"/api/assistant/conversations?project_id={project_a}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    # Access to project A itself is forbidden for B
    assert cross.status_code in {200, 403}
    if cross.status_code == 200:
        assert all(row["id"] != conv_a["id"] for row in cross.json()["conversations"])
    assert conv_b["id"] != conv_a["id"]


def test_tool_call_flow_with_mocked_gemini(client):
    project_id = _project_for(client)
    scanned = client.post(f"/api/projects/{project_id}/scans").json()
    bug = next(bug for bug in scanned["bugs"] if bug["suggested_patch"])
    bug_id = bug["id"]
    conv = client.post(
        "/api/assistant/conversations",
        json={"project_id": project_id},
    ).json()

    fake_payloads = [
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"functionCall": {"name": "explain_bug", "args": {"bug_id": bug_id}}},
                        ]
                    }
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": f"This bug ({bug_id}) is explained via a mocked tool call."}]
                    }
                }
            ]
        },
    ]

    with mock.patch("app.agent.runner.settings") as settings, mock.patch(
        "app.agent.runner._gemini_chat", side_effect=fake_payloads
    ):
        settings.gemini_configured = True
        response = client.post(
            f"/api/assistant/conversations/{conv['id']}/messages",
            json={"content": "Explain this bug", "bug_id": bug_id},
        )
    assert response.status_code == 200
    body = response.text
    assert "explain_bug" in body
    assert "mocked tool call" in body or "Explaining" in body


def test_secret_redaction():
    sample = "API_KEY = 'sk-live-51H7autopatchDemoKeyDoNotUse'\nprint(API_KEY)\n"
    cleaned = redact_text(sample)
    assert "sk-live" not in cleaned
    assert "***REDACTED***" in cleaned
    assert redact_path_name(".env") is True
    assert redact_path_name("marks.py") is False


def test_execute_search_tool_on_sample(client):
    project_id = _project_for(client)
    session = SessionLocal()
    try:
        project = session.get(Project, project_id)
        assert project is not None
        result, card = execute_tool(session, project, "search_code", {"query": "def"})
        assert card is None
        assert "hits" in result
    finally:
        session.close()
