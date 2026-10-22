"""Analytics & Monitoring tests — owned by Analytics Lead (Role 3).

Covers GET /api/stats/errors (normalized grouping) and /api/stats/summary + /api/health.
These endpoints existed only as a standalone file `role3_analytics.py` in the analytics branch
and had no integration tests.
"""
"""(Role 3 tests) get_db and TestClient fixtures come from tests/conftest.py."""
from datetime import datetime, timedelta, timezone
from app.crud import create_upload, bulk_create_log_entries

def test_stats_errors_grouping_and_normalization(client, db_session):
    # Create data with recurring normalized messages
    upload = create_upload(db_session, "analytics.log", 3, 3, 0, "completed")
    now = datetime.now(timezone.utc)
    entries = [
        {"timestamp": now, "severity": "ERROR", "service": "auth-service", "request_id": "req-1", "message": "Database connection timeout"},
        {"timestamp": now, "severity": "ERROR", "service": "auth-service", "request_id": "req-2", "message": "Database connection timeout"},
        # Same pattern with different number should group: "timeout after 5023ms" vs "3102ms"
        {"timestamp": now, "severity": "ERROR", "service": "payment-service", "request_id": "req-3", "message": "timeout after 5023ms"},
        {"timestamp": now, "severity": "ERROR", "service": "payment-service", "request_id": "req-4", "message": "timeout after 3102ms"},
    ]
    bulk_create_log_entries(db_session, upload.id, entries)
    resp = client.get("/api/stats/errors?top=10")
    assert resp.status_code == 200
    errors = resp.json()["errors"]
    # Should have 2 groups: "Database connection timeout" (count 2) and normalized timeout (count 2)
    assert len(errors) == 2
    # Find the timeout group
    timeout_group = next(g for g in errors if "timeout after" in g["message"].lower())
    assert timeout_group["count"] == 2
    assert len(timeout_group["sample_request_ids"]) == 2

def test_stats_summary_totals(client, db_session):
    upload = create_upload(db_session, "summary.log", 2, 2, 0, "completed")
    now = datetime.now(timezone.utc)
    bulk_create_log_entries(db_session, upload.id, [
        {"timestamp": now, "severity": "ERROR", "service": "auth-service", "request_id": None, "message": "err"},
        {"timestamp": now, "severity": "INFO", "service": "billing-service", "request_id": None, "message": "info"},
    ])
    resp = client.get("/api/stats/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entries"] == 2
    assert data["by_severity"]["ERROR"] == 1
    assert data["by_service"]["auth-service"] == 1

def test_health_returns_required_fields(client, db_session):
    # Ensure health matches teamguide contract
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"
    assert "total_entries" in data
    assert "last_upload" in data
    # Also service/version for Role 2 test compatibility
    assert data["service"] == "Log Search & Analyzer"


def test_stats_timeline_shape_and_zero_fill(client, db_session):
    upload = create_upload(db_session, "timeline.log", 3, 3, 0, "completed")
    base = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    bulk_create_log_entries(db_session, upload.id, [
        {"timestamp": base, "severity": "ERROR", "service": "s1", "request_id": None, "message": "boom"},
        {"timestamp": base + timedelta(minutes=30), "severity": "ERROR", "service": "s1", "request_id": None, "message": "boom"},
        {"timestamp": base + timedelta(hours=2), "severity": "INFO", "service": "s1", "request_id": None, "message": "ok"},
    ])
    resp = client.get("/api/stats/timeline?bucket=hour")
    assert resp.status_code == 200
    buckets = resp.json()["buckets"]
    assert len(buckets) == 3  # 10:00, 11:00 (zero-filled), 12:00
    assert buckets[0]["start"] == "2026-10-20T10:00:00Z"
    assert buckets[0]["ERROR"] == 2
    assert buckets[1]["ERROR"] == 0 and buckets[1]["INFO"] == 0
    assert buckets[2]["INFO"] == 1
    assert all({"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}.issubset(b) for b in buckets)


def test_stats_timeline_invalid_bucket_rejected(client):
    resp = client.get("/api/stats/timeline?bucket=minute")
    assert resp.status_code == 422


def _seed_streaks(db_session):
    """auth: 4 trailing errors · payment: streak broken by INFO · user: 2 errors."""
    upload = create_upload(db_session, "streaks.log", 8, 8, 0, "completed")
    t = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
    bulk_create_log_entries(db_session, upload.id, [
        {"timestamp": t + timedelta(minutes=0), "severity": "INFO", "service": "auth-service", "request_id": None, "message": "ok"},
        {"timestamp": t + timedelta(minutes=1), "severity": "ERROR", "service": "auth-service", "request_id": "r1", "message": "boom"},
        {"timestamp": t + timedelta(minutes=2), "severity": "ERROR", "service": "auth-service", "request_id": "r2", "message": "boom"},
        {"timestamp": t + timedelta(minutes=3), "severity": "CRITICAL", "service": "auth-service", "request_id": None, "message": "down"},
        {"timestamp": t + timedelta(minutes=1), "severity": "ERROR", "service": "payment-service", "request_id": None, "message": "boom"},
        {"timestamp": t + timedelta(minutes=2), "severity": "ERROR", "service": "payment-service", "request_id": None, "message": "boom"},
        {"timestamp": t + timedelta(minutes=3), "severity": "INFO", "service": "payment-service", "request_id": None, "message": "recovered"},
        {"timestamp": t + timedelta(minutes=4), "severity": "ERROR", "service": "user-service", "request_id": None, "message": "boom"},
        {"timestamp": t + timedelta(minutes=5), "severity": "ERROR", "service": "user-service", "request_id": None, "message": "boom"},
    ])


def test_stats_streaks_trailing_semantics(client, db_session):
    _seed_streaks(db_session)
    resp = client.get("/api/stats/streaks?min=3")
    assert resp.status_code == 200
    streaks = resp.json()["streaks"]
    # Only auth-service qualifies: payment's streak was closed by INFO; user's is 2 < min
    assert len(streaks) == 1
    s = streaks[0]
    assert s["service"] == "auth-service"
    assert s["streak"] == 3
    assert s["last_message"] == "down"
    assert s["since"].endswith("Z") and s["last_seen"].endswith("Z")
    assert set(s["sample_request_ids"]) == {"r1", "r2"}


def test_stats_streaks_min_param(client, db_session):
    _seed_streaks(db_session)
    streaks = client.get("/api/stats/streaks?min=2").json()["streaks"]
    assert len(streaks) == 2
    assert streaks[0]["streak"] >= streaks[1]["streak"]  # sorted desc
    none = client.get("/api/stats/streaks?min=5").json()["streaks"]
    assert none == []


def test_stats_streaks_invalid_min_rejected(client):
    assert client.get("/api/stats/streaks?min=1").status_code == 422
