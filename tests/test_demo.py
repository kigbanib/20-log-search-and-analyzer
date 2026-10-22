"""Demo scenario endpoint tests — owned by QA & DevOps (Role 5).

Covers POST /api/demo/scenario/incident (scripted incident injection) and
POST /api/demo/reset (wipe + reseed baseline). Fixtures come from
tests/conftest.py.
"""
from datetime import datetime, timezone

from app.models import LogEntry


def test_incident_scenario_inserts_entries_and_hero_trace(client, db_session):
    resp = client.post("/api/demo/scenario/incident")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"] == "incident"
    assert body["inserted"] > 30
    hero = body["hero_request_id"]

    # The hero request must be traceable through the normal search endpoint
    trace = client.get(f"/api/logs?request_id={hero}&limit=50").json()
    assert trace["total"] >= 6
    services = {e["service"] for e in trace["entries"]}
    assert len(services) >= 3  # api-gateway, payment-service, auth-service

    # Entries are recent (story spans the last ~40 minutes)
    now = datetime.now(timezone.utc).timestamp()
    stamps = [
        datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
        for e in trace["entries"]
    ]
    assert all(now - ts < 3600 for ts in stamps)


def test_incident_ends_with_consecutive_service_errors(client, db_session):
    """Prerequisite for streak detection: payment-service fails back-to-back."""
    client.post("/api/demo/scenario/incident")
    last = (
        db_session.query(LogEntry)
        .filter(LogEntry.service == "payment-service")
        .order_by(LogEntry.timestamp.desc())
        .limit(3)
        .all()
    )
    assert len(last) == 3
    assert all(e.severity in ("ERROR", "CRITICAL") for e in last)


def test_demo_reset_clears_and_reseeds_baseline(client, db_session):
    # Make a mess, then reset
    client.post("/api/demo/scenario/incident")
    resp = client.post("/api/demo/reset")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reset"] is True
    # Baseline comes from testdata/sample_valid.jsonl (500 valid lines)
    assert body["seeded"] == 500
    assert db_session.query(LogEntry).count() == 500
    # Incident data is gone
    gone = client.get("/api/logs?request_id=req-inc7001").json()
    assert gone["total"] == 0


def test_demo_reset_is_idempotent(client, db_session):
    client.post("/api/demo/reset")
    first = db_session.query(LogEntry).count()
    resp = client.post("/api/demo/reset")
    assert resp.status_code == 200
    assert db_session.query(LogEntry).count() == first


def test_streaks_fire_after_incident_scenario(client, db_session):
    """Cross-feature proof: incident seeding makes streak detection report a live fire."""
    client.post("/api/demo/scenario/incident")
    resp = client.get("/api/stats/streaks?min=3")
    assert resp.status_code == 200
    payment = next(
        (s for s in resp.json()["streaks"] if s["service"] == "payment-service"), None
    )
    assert payment is not None
    assert payment["streak"] >= 5
    assert payment["last_message"]
