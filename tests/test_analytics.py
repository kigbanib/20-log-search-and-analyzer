"""Analytics & Monitoring tests — owned by Analytics Lead (Role 3).

Covers GET /api/stats/errors (normalized grouping) and /api/stats/summary + /api/health.
These endpoints existed only as a standalone file `role3_analytics.py` in the analytics branch
and had no integration tests.
"""
from datetime import datetime, timezone
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
