"""API checks that do not need Gemini: upload, scan, explain, patch, export."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["demo_mode"] is True


def test_sample_scan_patch_and_export(client):
    created = client.post("/api/projects/sample", json={"sample_id": "marks_calculator"})
    assert created.status_code == 200, created.text
    project = created.json()
    assert project["languages"][0]["name"] == "Python"
    assert project["tree"]
    assert any(item["path"] == "marks.py" for item in project["important"]) or project["file_count"] >= 1

    scanned = client.post(f"/api/projects/{project['id']}/scans")
    assert scanned.status_code == 200, scanned.text
    body = scanned.json()
    assert body["mode"] == "demo"
    titles = {bug["bug_details"]["title"] for bug in body["bugs"]}
    assert any("100" in title or "Negative" in title for title in titles)
    actionable = [bug for bug in body["bugs"] if bug["bug_details"]["category"] != "style"]
    assert any(bug["suggested_patch"] for bug in actionable)
    bug = next(bug for bug in actionable if bug["suggested_patch"])
    assert bug["root_cause"]
    assert bug["trigger"]
    assert bug["severity_and_confidence"]["severity"] in {"critical", "high", "medium", "low"}
    assert "change_history" in bug

    translated = client.post(f"/api/bugs/{bug['id']}/translate", json={"language": "kn"})
    assert translated.status_code == 200
    assert translated.json()["text"]

    patch_id = bug["suggested_patch"][0]["id"]
    accepted = client.post(f"/api/patches/{patch_id}/decision", json={"action": "accept"})
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "applied"

    exported = client.get(f"/api/projects/{project['id']}/export/json")
    assert exported.status_code == 200
    assert "root_cause" in exported.text
    pdf = client.get(f"/api/projects/{project['id']}/export/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    zipped = client.get(f"/api/projects/{project['id']}/export/zip")
    assert zipped.status_code == 200
    assert zipped.content[:2] == b"PK"


def test_zip_slip_is_rejected(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.py", "print('no')\n")
    response = client.post(
        "/api/projects/upload",
        files={"file": ("evil.zip", buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 400


def test_github_url_validation(client):
    response = client.post("/api/projects/github", json={"url": "https://example.com/not/github"})
    assert response.status_code == 400
