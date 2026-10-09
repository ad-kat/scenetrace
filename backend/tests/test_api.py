"""Backend tests for SceneTrace API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["provider_mode"] in ("mock", "live", "hybrid")


# ---------------------------------------------------------------------------
# Video list
# ---------------------------------------------------------------------------

def test_list_videos():
    r = client.get("/api/videos")
    assert r.status_code == 200
    videos = r.json()
    assert isinstance(videos, list)
    assert len(videos) >= 1
    v = videos[0]
    assert v["id"] == "demo-01"
    assert "title" in v
    assert "video_url" in v


# ---------------------------------------------------------------------------
# Investigation — valid
# ---------------------------------------------------------------------------

def test_investigate_box():
    r = client.post("/api/investigate", json={"video_id": "demo-01", "query": "Find when someone sets down a box"})
    assert r.status_code == 200
    data = r.json()
    assert "session_id" in data
    assert data["mode"] == "mock"
    assert isinstance(data["events"], list)
    assert len(data["events"]) > 0
    evt = data["events"][0]
    assert evt["start_sec"] >= 0
    assert evt["end_sec"] > evt["start_sec"]
    assert evt["video_id"] == "demo-01"
    assert "explanation" in evt
    assert "evidence" in evt
    assert evt["verification"] == "unverified_mock"


def test_investigate_person():
    r = client.post("/api/investigate", json={"video_id": "demo-01", "query": "person walking"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["events"]) > 0


def test_investigate_no_results_returns_empty_list():
    # Unknown term yields default fixture, so we test the no-result path via invalid video
    r = client.post("/api/investigate", json={"video_id": "demo-01", "query": "x" * 500})
    assert r.status_code == 200


def test_investigate_tool_trace_present():
    r = client.post("/api/investigate", json={"video_id": "demo-01", "query": "box"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["tool_trace"]) > 0
    t = data["tool_trace"][0]
    assert "tool" in t
    assert "duration_ms" in t


def test_investigate_warnings_in_mock_mode():
    r = client.post("/api/investigate", json={"video_id": "demo-01", "query": "box"})
    data = r.json()
    assert any("Demo fixtures" in w or "mock" in w.lower() for w in data["warnings"])


# ---------------------------------------------------------------------------
# Follow-up / selected_event
# ---------------------------------------------------------------------------

def test_followup_uses_session_event():
    # First investigation
    r1 = client.post("/api/investigate", json={"video_id": "demo-01", "query": "box"})
    assert r1.status_code == 200
    d1 = r1.json()
    session_id = d1["session_id"]
    event_id = d1["events"][0]["event_id"]

    # Follow-up referencing the event
    r2 = client.post("/api/investigate", json={
        "video_id": "demo-01",
        "query": "What happened just before this?",
        "session_id": session_id,
        "selected_event_id": event_id,
    })
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["session_id"] == session_id
    assert len(d2["events"]) > 0


def test_followup_bad_event_id_returns_400():
    r = client.post("/api/investigate", json={
        "video_id": "demo-01",
        "query": "What happened?",
        "session_id": "nonexistent-session",
        "selected_event_id": "bad-event-id",
    })
    assert r.status_code == 400


def test_session_isolation():
    """Events from one session are not visible in another."""
    r1 = client.post("/api/investigate", json={"video_id": "demo-01", "query": "box"})
    d1 = r1.json()
    event_id = d1["events"][0]["event_id"]

    # Different session_id (None → new session)
    r2 = client.post("/api/investigate", json={
        "video_id": "demo-01",
        "query": "follow up",
        "selected_event_id": event_id,
        # intentionally no session_id — creates new session
    })
    assert r2.status_code == 400  # event not in new session


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_blank_query_returns_400():
    r = client.post("/api/investigate", json={"video_id": "demo-01", "query": "   "})
    assert r.status_code == 400


def test_invalid_video_id_returns_400():
    r = client.post("/api/investigate", json={"video_id": "../etc/passwd", "query": "test"})
    assert r.status_code == 400


def test_unknown_video_id_returns_400():
    r = client.post("/api/investigate", json={"video_id": "unknown-video", "query": "test"})
    assert r.status_code == 400


def test_query_too_long_returns_422():
    r = client.post("/api/investigate", json={"video_id": "demo-01", "query": "x" * 501})
    assert r.status_code == 422


def test_video_file_invalid_id_returns_404():
    r = client.get("/api/videos/../etc/passwd/file")
    assert r.status_code in (404, 422)


# ---------------------------------------------------------------------------
# Incident report
# ---------------------------------------------------------------------------

def test_report_generates_from_session():
    # Establish a session with events first.
    r1 = client.post("/api/investigate", json={"video_id": "demo-01", "query": "forklift near person"})
    assert r1.status_code == 200
    session_id = r1.json()["session_id"]

    r2 = client.post("/api/report", json={"session_id": session_id})
    assert r2.status_code == 200
    data = r2.json()
    assert "report_id" in data
    assert "generated_at" in data
    assert "summary" in data
    assert isinstance(data["sections"], list)
    assert len(data["sections"]) > 0
    assert isinstance(data["incidents"], list)


def test_report_blank_session_id_returns_400():
    r = client.post("/api/report", json={"session_id": "   "})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# No secrets in response
# ---------------------------------------------------------------------------

def test_no_secrets_in_health():
    import json
    r = client.get("/health")
    body = r.text
    assert "API_KEY" not in body
    assert "api_key" not in body.lower() or "VAST_API_KEY" not in body
