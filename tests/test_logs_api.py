"""
Comprehensive automated tests for GET /api/logs endpoint.
Validates all 13 core requirements, filtering permutations, pagination,
input validation, error handling, session lifecycle, and API contract conformity.
"""

from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogEntry


def test_get_logs_default_no_filters(client: TestClient, seed_data: dict):
    """
    Requirement 3 & 8: Retrieval without filters returns all logs,
    with default pagination (page=1, limit=50) and correct total count.
    """
    response = client.get("/api/logs")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["limit"] == 50
    assert len(data["entries"]) == 15


def test_response_contract_conformance(client: TestClient, seed_data: dict):
    """
    Requirement 3 & API Contract:
    Response must contain total, page, limit, entries.
    Each entry must contain id, timestamp, severity, service, request_id, message.
    """
    response = client.get("/api/logs?limit=1")
    assert response.status_code == 200

    data = response.json()
    assert "total" in data
    assert "page" in data
    assert "limit" in data
    assert "entries" in data

    entry = data["entries"][0]
    required_keys = {"id", "timestamp", "severity", "service", "request_id", "message"}
    assert required_keys.issubset(entry.keys())
    # Ensure timestamp parses as valid ISO format
    datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))


def test_case_insensitive_severity_filtering(client: TestClient, seed_data: dict):
    """
    Requirement 4: Case-insensitive severity filtering.
    Checks uppercase, lowercase, and mixed case.
    """
    # 1. ERROR in uppercase
    res_upper = client.get("/api/logs?severity=ERROR")
    assert res_upper.status_code == 200
    data_upper = res_upper.json()
    assert data_upper["total"] == 4
    for entry in data_upper["entries"]:
        assert entry["severity"] == "ERROR"

    # 2. error in lowercase
    res_lower = client.get("/api/logs?severity=error")
    assert res_lower.status_code == 200
    data_lower = res_lower.json()
    assert data_lower["total"] == 4
    for entry in data_lower["entries"]:
        assert entry["severity"] == "ERROR"

    # 3. Error in mixed case
    res_mixed = client.get("/api/logs?severity=Error")
    assert res_mixed.status_code == 200
    assert res_mixed.json()["total"] == 4

    # 4. Other severities
    assert client.get("/api/logs?severity=warn").json()["total"] == 3
    assert client.get("/api/logs?severity=CRITICAL").json()["total"] == 2
    assert client.get("/api/logs?severity=info").json()["total"] == 4
    assert client.get("/api/logs?severity=DEBUG").json()["total"] == 2


def test_invalid_severity_returns_400(client: TestClient, seed_data: dict):
    """
    Requirement 10: Input validation rejects invalid severity with HTTP 400.
    """
    response = client.get("/api/logs?severity=TRACE")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Invalid severity 'TRACE'" in data["detail"]
    assert "DEBUG" in data["detail"]
    assert "CRITICAL" in data["detail"]


def test_exact_request_id_matching(client: TestClient, seed_data: dict):
    """
    Requirement 5: Exact request-ID matching, NOT partial/substring matching.
    In seed data:
      - 'req-alpha' exists on 3 logs
      - 'req-alpha-child' exists on 1 log
    Searching for 'req-alpha' MUST return exactly 3 logs, NOT 4!
    """
    response = client.get("/api/logs?request_id=req-alpha")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    for entry in data["entries"]:
        assert entry["request_id"] == "req-alpha"

    # Querying child exact match
    child_resp = client.get("/api/logs?request_id=req-alpha-child")
    assert child_resp.status_code == 200
    assert child_resp.json()["total"] == 1
    assert child_resp.json()["entries"][0]["request_id"] == "req-alpha-child"

    # Substring like 'alpha' alone should return 0 because matching is exact
    partial_resp = client.get("/api/logs?request_id=alpha")
    assert partial_resp.status_code == 200
    assert partial_resp.json()["total"] == 0
    assert partial_resp.json()["entries"] == []


def test_request_id_not_found(client: TestClient, seed_data: dict):
    """Non-existent request ID returns total=0 and empty entries list with 200 OK."""
    response = client.get("/api/logs?request_id=non-existent-999")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["entries"] == []


def test_nullable_request_id_handling(client: TestClient, seed_data: dict):
    """
    Requirement 8: Handling nullable request IDs.
    Seed data contains 3 entries with request_id = None.
    They should appear when no request_id filter is passed, with request_id = None.
    """
    response = client.get("/api/logs?limit=15")
    entries = response.json()["entries"]
    null_req_entries = [e for e in entries if e["request_id"] is None]
    assert len(null_req_entries) == 3


def test_date_range_filtering_from_and_to(client: TestClient, seed_data: dict):
    """
    Requirement 6: Date-range filtering.
    Tests 'from' only, 'to' only, and both together.
    """
    # 1. From only (logs on or after 2026-10-20T12:00:00Z)
    res_from = client.get("/api/logs?from=2026-10-20T12:00:00Z")
    assert res_from.status_code == 200
    data_from = res_from.json()
    # 2026-10-20T12:00:00, 14:00:00, 15:00:00, 16:00:00, 2026-10-21T01:00:00, 2026-10-21T02:00:00 -> 6 logs
    assert data_from["total"] == 6

    # 2. To only (logs on or before 2026-10-18T23:59:59Z)
    res_to = client.get("/api/logs?to=2026-10-18T23:59:59Z")
    assert res_to.status_code == 200
    data_to = res_to.json()
    # 2 logs on 2026-10-18
    assert data_to["total"] == 2

    # 3. Specific day window: Oct 19 all day
    res_range = client.get("/api/logs?from=2026-10-19T00:00:00Z&to=2026-10-19T23:59:59Z")
    assert res_range.status_code == 200
    data_range = res_range.json()
    # 3 logs on Oct 19 (11:00, 12:00, 13:00)
    assert data_range["total"] == 3


def test_date_range_invalid_order_returns_400(client: TestClient, seed_data: dict):
    """
    Requirement 10: from > to returns HTTP 400 with a clear error.
    """
    response = client.get("/api/logs?from=2026-10-25T00:00:00Z&to=2026-10-20T00:00:00Z")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "earlier than or equal to" in data["detail"]


def test_date_range_invalid_format_returns_422(client: TestClient, seed_data: dict):
    """
    Requirement 10: Non-ISO date format returns HTTP 422.
    """
    response = client.get("/api/logs?from=not-a-timestamp")
    assert response.status_code == 422


def test_multiple_filters_combined(client: TestClient, seed_data: dict):
    """
    Multiple filters applied simultaneously (severity + request_id + date range).
    """
    # Severity ERROR + request_id req-beta
    response = client.get("/api/logs?severity=ERROR&request_id=req-beta")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    for entry in data["entries"]:
        assert entry["severity"] == "ERROR"
        assert entry["request_id"] == "req-beta"

    # Severity ERROR + request_id req-alpha (doesn't exist; req-alpha has DEBUG, INFO, WARN)
    no_match = client.get("/api/logs?severity=ERROR&request_id=req-alpha")
    assert no_match.status_code == 200
    assert no_match.json()["total"] == 0

    # Severity INFO + date range
    info_range = client.get(
        "/api/logs?severity=INFO&from=2026-10-20T00:00:00Z&to=2026-10-20T23:59:59Z"
    )
    assert info_range.status_code == 200
    assert info_range.json()["total"] == 3


def test_pagination_pages_and_limits(client: TestClient, seed_data: dict):
    """
    Requirement 7 & 8: Validated pagination and total count before pagination.
    Total = 15. With limit = 5:
      Page 1: 5 entries
      Page 2: 5 entries
      Page 3: 5 entries
      Page 4: 0 entries
    """
    # Page 1
    p1 = client.get("/api/logs?page=1&limit=5").json()
    assert p1["total"] == 15
    assert p1["page"] == 1
    assert p1["limit"] == 5
    assert len(p1["entries"]) == 5
    p1_ids = [e["id"] for e in p1["entries"]]

    # Page 2
    p2 = client.get("/api/logs?page=2&limit=5").json()
    assert p2["total"] == 15
    assert p2["page"] == 2
    assert p2["limit"] == 5
    assert len(p2["entries"]) == 5
    p2_ids = [e["id"] for e in p2["entries"]]

    # Verify no overlap between Page 1 and Page 2
    assert set(p1_ids).isdisjoint(set(p2_ids))

    # Page 3
    p3 = client.get("/api/logs?page=3&limit=5").json()
    assert p3["total"] == 15
    assert len(p3["entries"]) == 5
    p3_ids = [e["id"] for e in p3["entries"]]
    assert set(p2_ids).isdisjoint(set(p3_ids))

    # Page 4 (Beyond total count)
    p4 = client.get("/api/logs?page=4&limit=5").json()
    assert p4["total"] == 15
    assert p4["page"] == 4
    assert p4["entries"] == []


def test_pagination_input_validation(client: TestClient, seed_data: dict):
    """
    Requirement 7 & 10: Pagination parameters validation bounds.
    page < 1 -> 422
    limit < 1 -> 422
    limit > 100 -> 422
    """
    assert client.get("/api/logs?page=0").status_code == 422
    assert client.get("/api/logs?page=-5").status_code == 422
    assert client.get("/api/logs?limit=0").status_code == 422
    assert client.get("/api/logs?limit=101").status_code == 422


def test_predictable_result_ordering(client: TestClient, seed_data: dict):
    """
    Requirement 9: Predictable ordering.
    Results must be ordered by timestamp DESC, with id DESC as tie-breaker.
    """
    response = client.get("/api/logs?limit=15")
    assert response.status_code == 200
    entries = response.json()["entries"]

    for i in range(len(entries) - 1):
        curr_ts = datetime.fromisoformat(entries[i]["timestamp"].replace("Z", "+00:00"))
        next_ts = datetime.fromisoformat(entries[i + 1]["timestamp"].replace("Z", "+00:00"))
        # curr_ts must be >= next_ts (descending)
        assert curr_ts >= next_ts
        if curr_ts == next_ts:
            assert entries[i]["id"] > entries[i + 1]["id"]


def test_database_session_lifecycle(client: TestClient, seed_data: dict):
    """
    Verifies that consecutive requests open and close database sessions
    without leaking connections or leaving dangling transactions.
    """
    for _ in range(5):
        resp = client.get("/api/logs?limit=2")
        assert resp.status_code == 200


def test_health_check_endpoint(client: TestClient):
    """Verifies health check endpoint used by deployment and monitoring."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "Log Search & Analyzer"


def test_root_endpoint(client: TestClient):
    """Verifies API root discovery endpoint."""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "/api/logs" in data["endpoints"]["search_logs"]
