"""Health reports the real Gemini state, and pasted keys are cleaned up."""

from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.llm import gemini
from app.main import app


def test_pasted_key_is_cleaned():
    assert Settings(gemini_api_key=' "AQ.abc"\n').gemini_api_key == "AQ.abc"
    assert Settings(gemini_api_key="GEMINI_API_KEY=AQ.xyz").gemini_api_key == "AQ.xyz"


def test_health_reports_rejected_key(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(gemini, "_key_rejected_until", 0.0)
    gemini._cooling_until.clear()
    assert client.get("/api/health").json()["gemini_status"] == "online"

    gemini.mark_key_rejected("401 UNAUTHENTICATED: API key not valid test-key")
    body = client.get("/api/health").json()
    assert body["gemini_status"] == "key_rejected"
    assert "test-key" not in body["gemini_last_error"]
    assert "API key not valid" in body["gemini_last_error"]
    monkeypatch.setattr(gemini, "_key_rejected_until", 0.0)


def test_health_without_key_is_off(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert TestClient(app).get("/api/health").json()["gemini_status"] == "off"
