"""
Integration and edge-case tests demonstrating inter-role workflows:
- Role 1 (Ingestion): Upload creation and bulk log ingestion
- Role 2 (Search API): Searching newly ingested logs
- Role 3 (Analytics): Aggregating logs by severity and service
- Edge Cases: Exact timestamp boundaries, multiline messages, special characters in request IDs
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crud import create_upload, bulk_create_log_entries, get_logs
from app.models import LogEntry, Upload


def test_role_1_ingestion_to_role_2_search_workflow(db_session: Session, client: TestClient):
    """
    Simulates Role 1 parsing a log file, saving it via Upload and bulk LogEntries,
    and then Role 2 immediately serving them via GET /api/logs.
    """
    # 1. Role 1 creates an Upload record
    upload = create_upload(
        db=db_session,
        filename="nginx-access.log",
        total_lines=3,
        parsed_lines=3,
        failed_lines=0,
        status="completed",
    )
    assert upload.id is not None

    # 2. Role 1 parses log lines and bulk-inserts them
    raw_parsed_data = [
        {
            "timestamp": datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc),
            "severity": "info",  # Lowercase from raw parser
            "service": "nginx",
            "request_id": "req-live-01",
            "message": "GET /api/v1/users 200 45ms",
        },
        {
            "timestamp": datetime(2026, 10, 20, 10, 0, 5, tzinfo=timezone.utc),
            "severity": "WARN",
            "service": "nginx",
            "request_id": "req-live-02",
            "message": "GET /api/v1/orders 499 5002ms Client Closed Request",
        },
        {
            "timestamp": datetime(2026, 10, 20, 10, 0, 10, tzinfo=timezone.utc),
            "severity": "error",
            "service": "nginx",
            "request_id": "req-live-03",
            "message": "POST /api/v1/checkout 500 120ms Internal Server Error\nTraceback: Database connection lost",
        },
    ]

    count = bulk_create_log_entries(db_session, upload.id, raw_parsed_data)
    assert count == 3

    # 3. Role 2 API retrieves them via HTTP
    response = client.get("/api/logs?severity=ERROR")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["entries"][0]["request_id"] == "req-live-03"
    assert "Traceback: Database connection lost" in data["entries"][0]["message"]


def test_role_3_analytics_compatibility(db_session: Session):
    """
    Simulates Role 3 querying LogEntry directly for analytics (severity counts, top error services).
    Ensures models and indexes satisfy Role 3's requirements.
    """
    upload = create_upload(db_session, "analytics-test.log", 3, 3, 0, "completed")
    entries = [
        {"timestamp": datetime.now(timezone.utc), "severity": "ERROR", "service": "auth", "request_id": None, "message": "err 1"},
        {"timestamp": datetime.now(timezone.utc), "severity": "ERROR", "service": "billing", "request_id": None, "message": "err 2"},
        {"timestamp": datetime.now(timezone.utc), "severity": "WARN", "service": "auth", "request_id": None, "message": "warn 1"},
    ]
    bulk_create_log_entries(db_session, upload.id, entries)

    # Role 3: Count by severity
    severity_counts = dict(
        db_session.execute(
            select(LogEntry.severity, func.count(LogEntry.id)).group_by(LogEntry.severity)
        ).all()
    )
    assert severity_counts["ERROR"] == 2
    assert severity_counts["WARN"] == 1

    # Role 3: Error count grouped by service
    error_by_service = dict(
        db_session.execute(
            select(LogEntry.service, func.count(LogEntry.id))
            .where(LogEntry.severity == "ERROR")
            .group_by(LogEntry.service)
        ).all()
    )
    assert error_by_service["auth"] == 1
    assert error_by_service["billing"] == 1


def test_date_range_equal_from_and_to_boundary(db_session: Session, client: TestClient):
    """
    Edge case: When 'from' equals 'to', it should match entries with that exact timestamp.
    """
    upload = create_upload(db_session, "exact-ts.log", 2, 2, 0, "completed")
    exact_ts = datetime(2026, 10, 20, 15, 30, 0, tzinfo=timezone.utc)
    other_ts = datetime(2026, 10, 20, 15, 30, 1, tzinfo=timezone.utc)

    bulk_create_log_entries(
        db_session,
        upload.id,
        [
            {"timestamp": exact_ts, "severity": "INFO", "service": "cron", "request_id": None, "message": "Exact match"},
            {"timestamp": other_ts, "severity": "INFO", "service": "cron", "request_id": None, "message": "One second later"},
        ],
    )

    iso_exact = "2026-10-20T15:30:00Z"
    resp = client.get(f"/api/logs?from={iso_exact}&to={iso_exact}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entries"][0]["message"] == "Exact match"


def test_special_characters_in_request_id(db_session: Session, client: TestClient):
    """
    Edge case: Request IDs containing dashes, colons, dots, underscores, or slashes.
    """
    upload = create_upload(db_session, "special-req.log", 1, 1, 0, "completed")
    special_req_id = "req_2026.10.20-auth:8f3k2/worker-01"

    bulk_create_log_entries(
        db_session,
        upload.id,
        [
            {
                "timestamp": datetime.now(timezone.utc),
                "severity": "INFO",
                "service": "api",
                "request_id": special_req_id,
                "message": "Special ID handled",
            }
        ],
    )

    resp = client.get(f"/api/logs?request_id={special_req_id}")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["entries"][0]["request_id"] == special_req_id
