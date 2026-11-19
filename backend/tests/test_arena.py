"""Break-It attacks, the AI Debate Room, the Repair Race, and Gemini model fallback."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.arena.attack import build_cases, safe_expression
from app.arena.context import Target
from app.config import settings
from app.db import init_db
from app.limiter import limiter
from app.llm import gemini
from app.main import app

AVERAGE = "def average(values):\n    return sum(values) / len(values)\n\nprint(average([3, 4]))\n"


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.hits.clear()
    gemini._cooling_until.clear()


def _events(response) -> list[dict]:
    return [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]


@pytest.fixture(scope="module")
def marks_patch(client) -> str:
    project = client.post("/api/projects/sample", json={"sample_id": "marks_calculator"}).json()
    scan = client.post(f"/api/projects/{project['id']}/scans").json()
    bug = next(bug for bug in scan["bugs"] if bug["bug_details"]["rule_id"] == "empty_collection_divisor")
    return bug["suggested_patch"][0]["id"]


def test_attack_mode_scores_old_and_new_code(client, marks_patch):
    response = client.post(f"/api/patches/{marks_patch}/attack")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["function"] == "calculate"
    assert 10 <= body["total"] <= 15
    assert body["old_crashed"] >= 1
    assert body["old_failed"] == body["old_crashed"] + body["old_accepted_bad_input"]
    assert body["headline"] == f"Old code failed {body['old_failed']}/{body['total']} · New code survived {body['new_survived']}/{body['total']}"
    empty = next(row for row in body["cases"] if row["args"] == ["[]"])
    assert empty["old"]["status"] == "crashed"
    assert "ZeroDivisionError" in empty["old"]["detail"]
    assert empty["new"]["status"] == "rejected"
    assert empty["verdict"] == "blocked"


def test_attack_inputs_mix_gemini_and_rules(monkeypatch):
    payload = {
        "cases": [
            {"label": "empty", "args": ["[]"], "wrong_type": False},
            {"label": "giant power", "args": ["10**10**10"]},
            {"label": "sneaky import", "args": ["__import__('os').system('id')"]},
            {"label": "infinity", "args": ["[float('inf')]"]},
        ]
    }
    monkeypatch.setattr(gemini, "ask_gemini", lambda *args, **kwargs: json.dumps(payload))
    target = Target("average", "", ["values"], "def average(values):\n    return sum(values) / len(values)\n")
    cases = build_cases(target)
    assert [case.origin for case in cases[:2]] == ["gemini", "gemini"]
    assert all("__import__" not in arg and "10**10**10" not in arg for case in cases for arg in case.args)
    assert 10 <= len(cases) <= 15
    assert len({tuple(case.args) for case in cases}) == len(cases)


def test_safe_expression_whitelist():
    for good in ["[]", "None", "-10**9", "float('nan')", "'a' * 1000", "[1, 'two', 3]", "{'a': 1}"]:
        assert safe_expression(good), good
    for bad in ["__import__('os')", "open('x')", "10**10**10", "'a' * 10**9", "lambda: 1", "[x for x in range(3)]"]:
        assert not safe_expression(bad), bad


def test_debate_falls_back_to_test_evidence_without_gemini(client, marks_patch):
    response = client.post(f"/api/patches/{marks_patch}/debate", json={})
    assert response.status_code == 200
    events = _events(response)
    turns = [event for event in events if event["type"] == "turn"]
    assert len(turns) == 6
    assert {turn["role"] for turn in turns} == {"fixer", "breaker"}
    assert all(turn["engine"] == "rules" for turn in turns)
    verdict = next(event for event in events if event["type"] == "verdict")
    assert verdict["verdict"] in {"safe", "needs_changes"}
    assert 0 <= verdict["confidence"] <= 100
    assert events[-1]["type"] == "done"


def test_debate_with_gemini_and_mid_debate_dropout(client, marks_patch, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls = {"count": 0}

    def fake_ask(prompt, json_output=False, timeout=None, prefer_fast=False):
        calls["count"] += 1
        if json_output:
            return json.dumps({"verdict": "safe", "confidence": 88, "reason": "The guard handles empty input."})
        return "Breaker: what about an empty list?" if "You are Breaker" in prompt else "The new guard raises ValueError first."

    monkeypatch.setattr(gemini, "ask_gemini", fake_ask)
    events = _events(client.post(f"/api/patches/{marks_patch}/debate", json={}))
    turns = [event for event in events if event["type"] == "turn"]
    assert len(turns) == 6 and all(turn["engine"] == "gemini" for turn in turns)
    assert turns[0]["text"] == "what about an empty list?"
    verdict = next(event for event in events if event["type"] == "verdict")
    assert verdict == {"type": "verdict", "verdict": "safe", "confidence": 88, "reason": "The guard handles empty input.", "engine": "gemini"}

    def flaky(prompt, json_output=False, timeout=None, prefer_fast=False):
        flaky.calls += 1
        if flaky.calls > 2:
            raise gemini.GeminiError("503 overloaded")
        return "A point."

    flaky.calls = 0
    monkeypatch.setattr(gemini, "ask_gemini", flaky)
    events = _events(client.post(f"/api/patches/{marks_patch}/debate", json={}))
    turns = [event for event in events if event["type"] == "turn"]
    assert len(turns) == 6
    assert [turn["engine"] for turn in turns] == ["gemini", "gemini", "rules", "rules", "rules", "rules"]
    assert any(event["type"] == "notice" for event in events)
    assert next(event for event in events if event["type"] == "verdict")["engine"] == "rules"


def test_overloaded_primary_model_falls_back_and_cools_down(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    tried = []

    def fake_generate(model, prompt, json_output=False, attempts=None, timeout=None):
        tried.append(model)
        if model == settings.gemini_model:
            raise gemini.GeminiError(f"{model} returned 503")
        return "ok"

    monkeypatch.setattr(gemini, "_generate", fake_generate)
    assert gemini.ask_gemini("hi") == "ok"
    assert tried == [settings.gemini_model, settings.gemini_fallback_model]
    tried.clear()
    assert gemini.ask_gemini("again") == "ok"
    assert tried == [settings.gemini_fallback_model]


def test_repair_race_runs_the_real_pipeline(client):
    response = client.post("/api/race", json={"code": AVERAGE})
    assert response.status_code == 200
    events = _events(response)
    stages = [event["stage"] for event in events if event["type"] == "stage"]
    assert stages == ["scanning", "bug_found", "fixed", "verified"]
    times = [event["t"] for event in events if event["type"] == "stage"]
    assert times == sorted(times)
    verified = next(event for event in events if event.get("stage") == "verified")
    assert verified["passed"] is True
    assert verified["failed_before"] is True
    finish = next(event for event in events if event["type"] == "finish")
    assert finish["result"] == "verified"


def test_repair_race_with_clean_code(client):
    events = _events(client.post("/api/race", json={"code": "def add(a, b):\n    return a + b\n"}))
    finish = next(event for event in events if event["type"] == "finish")
    assert finish["result"] == "clean"
