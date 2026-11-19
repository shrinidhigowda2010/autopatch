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


def _finding(source, symbol, line, title, category="logic"):
    from app.analysis.findings import Finding

    return Finding(
        rule_id="gemini_logic" if source == "gemini" else "negative_balance",
        file="bank.py", line=line, end_line=line, symbol=symbol, title=title, description="",
        category=category, severity="high", confidence=0.9 if source == "gemini" else 0.92, impact="",
        root_cause="x", trigger="", student_explanation="", explanation_kn="", explanation_hi="",
        source=source, needs_human_review=False, snippet="",
    )


def test_gemini_repeat_of_a_rule_finding_becomes_one_card():
    from app.analysis.merge import merge_findings

    rule = _finding("ast", "withdraw", 16, "Withdrawal can drive the balance below zero")
    other = _finding("ast", "deposit", 11, "Deposit accepts negative amounts")
    ai_twin = _finding("gemini", "Account.withdraw", 18, "Negative balance allowed")
    ai_new = _finding("gemini", "Account.close", 30, "Closing twice crashes", category="crash")
    merged = merge_findings([[rule, other], [ai_twin, ai_new]])
    assert [item.title for item in merged] == [
        "Withdrawal can drive the balance below zero",
        "Deposit accepts negative amounts",
        "Closing twice crashes",
    ]
    assert merged[0].source == "ast+gemini"
