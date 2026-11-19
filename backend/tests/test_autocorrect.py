"""Auto-Correct Mode: approve, reject, edit, rollback, auto-rollback on test failure."""

from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Patch


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


def _scan_with_patch(client: TestClient) -> tuple[str, str, str]:
    created = client.post("/api/projects/sample", json={"sample_id": "marks_calculator"})
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]
    scanned = client.post(f"/api/projects/{project_id}/scans")
    assert scanned.status_code == 200, scanned.text
    body = scanned.json()
    bug = next(bug for bug in body["bugs"] if bug["suggested_patch"])
    patch_id = bug["suggested_patch"][0]["id"]
    return project_id, body["id"], patch_id


def test_approve_applies_patch(client):
    project_id, _scan_id, patch_id = _scan_with_patch(client)
    # Approve without live verify to keep the test fast and deterministic.
    response = client.post(
        f"/api/patches/{patch_id}/decision",
        json={"action": "approve", "verify_tests": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "applied"
    versions = client.get(f"/api/projects/{project_id}/versions")
    assert versions.status_code == 200
    nums = [row["version"] for row in versions.json()["versions"]]
    assert 0 in nums
    assert max(nums) >= 1


def test_reject_records_decision(client):
    _project_id, _scan_id, patch_id = _scan_with_patch(client)
    response = client.post(
        f"/api/patches/{patch_id}/reject",
        json={"note": "I prefer a different approach", "try_another": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"
    log = client.get(f"/api/projects/{_project_id}/decision-log")
    assert log.status_code == 200
    actions = [row["decision"] for row in log.json()["decisions"]]
    assert "rejected" in actions


def test_edit_applies_custom_code(client):
    project_id, _scan_id, patch_id = _scan_with_patch(client)
    # Read current after_code then tweak a comment line via edit endpoint.
    session = SessionLocal()
    try:
        patch = session.get(Patch, patch_id)
        assert patch is not None
        edited = patch.after_code + "\n# edited by human\n"
    finally:
        session.close()
    response = client.post(
        f"/api/patches/{patch_id}/edit",
        json={"edited_code": edited, "note": "manual tweak", "verify_tests": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "applied"
    assert "edited by human" in response.json()["after_code"]
    versions = client.get(f"/api/projects/{project_id}/versions").json()["versions"]
    assert any(row["version"] >= 1 for row in versions)


def test_rollback_last_and_all(client):
    project_id, _scan_id, patch_id = _scan_with_patch(client)
    accepted = client.post(
        f"/api/patches/{patch_id}/decision",
        json={"action": "accept", "verify_tests": False},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "applied"

    undone = client.post(f"/api/projects/{project_id}/rollback-last")
    assert undone.status_code == 200, undone.text
    assert undone.json()["version"] == 0

    # Apply again then rollback all
    # Patch may be proposed again after undo
    session = SessionLocal()
    try:
        patch = session.get(Patch, patch_id)
        assert patch is not None
        patch.status = "proposed"
        session.commit()
    finally:
        session.close()

    client.post(f"/api/patches/{patch_id}/decision", json={"action": "accept", "verify_tests": False})
    wiped = client.post(f"/api/projects/{project_id}/rollback-all")
    assert wiped.status_code == 200, wiped.text
    assert wiped.json()["version"] == 0


def test_auto_rollback_when_tests_fail(client):
    _project_id, _scan_id, patch_id = _scan_with_patch(client)

    with mock.patch("app.services._verify_workspace_tests", return_value=(False, {"regression_passed": False})):
        response = client.post(f"/api/patches/{patch_id}/approve")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rolled_back"] is True
    assert body["status"] == "proposed"
    assert "auto-rolled back" in (body.get("message") or "").lower() or body["rolled_back"]

    log = client.get(f"/api/projects/{_project_id}/decision-log")
    actions = [row["decision"] for row in log.json()["decisions"]]
    assert "rolled_back" in actions


def test_skip_patch(client):
    _project_id, _scan_id, patch_id = _scan_with_patch(client)
    response = client.post(f"/api/patches/{patch_id}/skip")
    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
