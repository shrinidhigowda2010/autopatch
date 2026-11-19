"""Multi-format upload: pasted code, links, PDFs, images, notebooks, archives."""

from __future__ import annotations

import io
import json
import tarfile

import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF
from PIL import Image

from app.db import init_db
from app.ingest import links
from app.ingest.links import resolve_link
from app.limiter import limiter
from app.main import app

BUGGY = "def average(values):\n    return sum(values) / len(values)\n\nprint(average([]))\n"


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_rate_limit():
    limiter.hits.clear()


def test_pasted_code_becomes_a_project_and_scans(client):
    created = client.post("/api/projects/paste", json={"files": [{"path": "", "content": BUGGY}]})
    assert created.status_code == 200, created.text
    project = created.json()
    assert project["source_type"] == "paste"
    assert project["languages"][0]["name"] == "Python"
    assert project["tree"][0]["path"] == "main.py"
    scanned = client.post(f"/api/projects/{project['id']}/scans")
    assert scanned.status_code == 200, scanned.text


def test_paste_rejects_path_traversal(client):
    response = client.post("/api/projects/paste", json={"files": [{"path": "../evil.py", "content": "x = 1\n"}]})
    assert response.status_code == 400


def test_github_blob_url_is_fetched_as_raw(client, monkeypatch):
    link = resolve_link("https://github.com/acme/tools/blob/main/src/stats.py")
    assert link.kind == "file"
    assert link.url == "https://raw.githubusercontent.com/acme/tools/main/src/stats.py"
    assert link.filename == "stats.py"
    assert resolve_link("https://github.com/acme/tools").kind == "repo"
    assert resolve_link("https://gist.github.com/someone/abc123def456").url.endswith("/gists/abc123def456")
    assert resolve_link("https://pastebin.com/Ab12Cd34").url == "https://pastebin.com/raw/Ab12Cd34"

    fetched = []

    def fake_get(url, max_bytes=None, accept="*/*"):
        fetched.append(url)
        return BUGGY.encode()

    monkeypatch.setattr("app.services.safe_get", fake_get)
    response = client.post("/api/projects/link", json={"url": "https://github.com/acme/tools/blob/main/src/stats.py"})
    assert response.status_code == 200, response.text
    assert fetched == ["https://raw.githubusercontent.com/acme/tools/main/src/stats.py"]
    assert response.json()["tree"][0]["path"] == "stats.py"


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8000/api/health", "http://localhost/secret.py", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/x.py"],
)
def test_private_addresses_are_blocked(client, url):
    response = client.post("/api/projects/link", json={"url": url})
    assert response.status_code == 400
    assert "private or local" in response.json()["detail"]


def test_non_http_links_are_blocked(client):
    response = client.post("/api/projects/link", json={"url": "file:///etc/passwd"})
    assert response.status_code == 400


def test_redirect_to_private_address_is_blocked(monkeypatch):
    checked = []

    def fake_check(url):
        checked.append(url)
        if "127.0.0.1" in url:
            raise links.IngestError("That link points to a private or local address, so FixPilot won't fetch it.")

    import httpx

    def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(links, "check_public", fake_check)
    monkeypatch.setattr(links.httpx, "Client", lambda **kwargs: real_client(transport=transport, **kwargs))
    with pytest.raises(links.IngestError, match="private or local"):
        links.safe_get("https://example.com/code.py")
    assert checked == ["https://example.com/code.py", "http://127.0.0.1/admin"]


def _pdf_with_code() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, "Assignment 3: write a function that returns the average of a list of marks.")
    pdf.set_font("Courier", size=10)
    for line in BUGGY.splitlines():
        pdf.cell(0, 6, line or " ", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_pdf_code_is_extracted_for_preview(client):
    response = client.post("/api/projects/extract", files={"file": ("homework.pdf", _pdf_with_code(), "application/pdf")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "pdf"
    code = next(item for item in body["files"] if item["language"] == "Python")
    assert code["path"].endswith(".py")
    assert code["content"].startswith("def average(values):")
    assert "return sum(values) / len(values)" in code["content"]
    assert "Assignment 3" not in code["content"]


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(out, format="PNG")
    return out.getvalue()


def test_image_code_is_read_by_gemini(client, monkeypatch):
    seen = {}

    def fake_vision(data, mime):
        seen["mime"] = mime
        return {"filename": "average.py", "code": BUGGY}

    monkeypatch.setattr("app.llm.gemini.read_code_from_image", fake_vision)
    response = client.post("/api/projects/extract", files={"file": ("shot.png", _png(), "image/png")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "image"
    assert body["files"][0]["path"] == "average.py"
    assert "def average" in body["files"][0]["content"]
    assert seen["mime"] == "image/png"


def test_image_without_ai_engine_explains_itself(client):
    response = client.post("/api/projects/extract", files={"file": ("shot.png", _png(), "image/png")})
    assert response.status_code == 503
    assert "Paste the code" in response.json()["detail"]


def test_fake_image_is_rejected(client):
    response = client.post("/api/projects/extract", files={"file": ("shot.png", b"print('hi')\n", "image/png")})
    assert response.status_code == 415


def test_unsupported_format_is_a_friendly_415(client):
    binary = bytes(range(256)) * 8
    response = client.post("/api/projects/upload", files={"file": ("program.exe", binary, "application/octet-stream")})
    assert response.status_code == 415
    assert "can't read" in response.json()["detail"]


def test_notebook_cells_become_python(client):
    notebook = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Notes"]},
            {"cell_type": "code", "source": ["!pip install numpy\n", "x = [1, 2]\n"]},
            {"cell_type": "code", "source": "print(sum(x) / len([]))"},
        ],
        "metadata": {"kernelspec": {"language": "python"}},
    }
    response = client.post(
        "/api/projects/extract", files={"file": ("lab.ipynb", json.dumps(notebook).encode(), "application/json")}
    )
    assert response.status_code == 200, response.text
    file = response.json()["files"][0]
    assert file["path"] == "lab.py"
    assert "# !pip install numpy" in file["content"]
    assert "# Notes" not in file["content"]


def test_many_code_languages_are_accepted(client):
    response = client.post(
        "/api/projects/upload",
        files={"file": ("Main.java", b'public class Main { public static void main(String[] a) { System.out.println(1/0); } }\n', "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["languages"][0]["name"] == "Java"


def test_tar_gz_upload_and_traversal_guard(client):
    good = io.BytesIO()
    with tarfile.open(fileobj=good, mode="w:gz") as archive:
        data = BUGGY.encode()
        info = tarfile.TarInfo("proj/stats.py")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    response = client.post("/api/projects/upload", files={"file": ("proj.tar.gz", good.getvalue(), "application/gzip")})
    assert response.status_code == 200, response.text
    assert response.json()["source_type"] == "zip"

    evil = io.BytesIO()
    with tarfile.open(fileobj=evil, mode="w") as archive:
        info = tarfile.TarInfo("../escape.py")
        info.size = 2
        archive.addfile(info, io.BytesIO(b"x\n"))
    response = client.post("/api/projects/upload", files={"file": ("evil.tar", evil.getvalue(), "application/x-tar")})
    assert response.status_code == 400


def test_secrets_are_redacted_before_gemini():
    from app.llm.gemini import _bundle

    bundle = _bundle([("app.py", 'API_KEY = "sk_live_abcdefghijklmnop1234"\n')])
    assert "sk_live_abcdefghijklmnop1234" not in bundle
