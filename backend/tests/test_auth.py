"""Auth: register, login, me, isolation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


def _register(client: TestClient, email: str, password: str = "password123", name: str = "Test User"):
    return client.post(
        "/api/auth/register",
        json={"full_name": name, "email": email, "password": password, "role": "student"},
    )


def test_register_returns_coder_id_and_token(client):
    response = _register(client, "alice@example.com", name="Alice")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["coder_id"].startswith("FP-CODER-")
    assert len(body["coder_id"]) == len("FP-CODER-XXXXX")
    assert body["user"]["email"] == "alice@example.com"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_login_with_email(client):
    _register(client, "bob@example.com", password="secretpass", name="Bob")
    response = client.post(
        "/api/auth/login",
        json={"identifier": "bob@example.com", "password": "secretpass"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]
    assert response.json()["coder_id"].startswith("FP-CODER-")


def test_login_with_coder_id(client):
    created = _register(client, "carol@example.com", password="secretpass", name="Carol")
    coder_id = created.json()["coder_id"]
    response = client.post(
        "/api/auth/login",
        json={"identifier": coder_id, "password": "secretpass"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["coder_id"] == coder_id


def test_wrong_password(client):
    _register(client, "dave@example.com", password="correcthorse")
    response = client.post(
        "/api/auth/login",
        json={"identifier": "dave@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert "password" in response.json()["detail"].lower() or "incorrect" in response.json()["detail"].lower()


def test_protected_route_without_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_token(client):
    created = _register(client, "erin@example.com", name="Erin")
    token = created.json()["access_token"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Erin"
    assert "stats" in body
    assert "member_since" in body["stats"]


def test_per_user_history_isolation(client):
    a = _register(client, "user-a@example.com", name="User A")
    b = _register(client, "user-b@example.com", name="User B")
    token_a = a.json()["access_token"]
    token_b = b.json()["access_token"]

    project_a = client.post(
        "/api/projects/sample",
        json={"sample_id": "marks_calculator"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert project_a.status_code == 200
    id_a = project_a.json()["id"]

    project_b = client.post(
        "/api/projects/sample",
        json={"sample_id": "div_zero"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert project_b.status_code == 200
    id_b = project_b.json()["id"]

    list_a = client.get("/api/projects", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    ids_a = {row["id"] for row in list_a.json()}
    assert id_a in ids_a
    assert id_b not in ids_a

    list_b = client.get("/api/projects", headers={"Authorization": f"Bearer {token_b}"})
    ids_b = {row["id"] for row in list_b.json()}
    assert id_b in ids_b
    assert id_a not in ids_b

    # User B cannot access user A's project
    denied = client.get(f"/api/projects/{id_a}", headers={"Authorization": f"Bearer {token_b}"})
    assert denied.status_code == 403

    hist_a = client.get("/api/auth/history", headers={"Authorization": f"Bearer {token_a}"})
    assert hist_a.status_code == 200
    hist_ids = {row["id"] for row in hist_a.json()["projects"]}
    assert id_a in hist_ids
    assert id_b not in hist_ids


def test_short_password_rejected(client):
    response = client.post(
        "/api/auth/register",
        json={"full_name": "Tiny", "email": "tiny@example.com", "password": "short", "role": "student"},
    )
    assert response.status_code == 422


def test_guest_can_still_load_sample(client):
    response = client.post("/api/projects/sample", json={"sample_id": "marks_calculator"})
    assert response.status_code == 200
    assert response.json()["is_guest"] is True


def test_legacy_ap_coder_ids_still_sign_in(client):
    from app.db import SessionLocal
    from app.models import User

    created = _register(client, "legacy@example.com", password="secretpass", name="Legacy")
    new_id = created.json()["coder_id"]
    legacy_id = "AP-CODER-" + new_id.removeprefix("FP-CODER-")
    with SessionLocal() as session:
        user = session.query(User).filter(User.coder_id == new_id).one()
        user.coder_id = legacy_id
        session.commit()
    for typed in (legacy_id, legacy_id.lower(), new_id):
        response = client.post("/api/auth/login", json={"identifier": typed, "password": "secretpass"})
        assert response.status_code == 200, typed
        assert response.json()["coder_id"] == legacy_id
