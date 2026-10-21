"""Upload endpoint integration tests — owned by Ingestion & Parser Lead (Role 1).

These tests were missing in the isolated branch (which used data.json)
and are required for the merged develop to validate the DB-backed ingestion.
"""
import io
import json
from fastapi.testclient import TestClient

def test_upload_valid_file(client: TestClient):
    # Minimal valid JSONL
    lines = [
        json.dumps({"timestamp":"2026-10-20T10:15:04Z","severity":"ERROR","service":"auth-service","request_id":"req-8f3k2","message":"Database connection timeout"}),
        json.dumps({"timestamp":"2026-10-20T10:16:00Z","severity":"INFO","service":"api-gateway","request_id":"req-8f3k2","message":"Request completed"}),
    ]
    content = "\n".join(lines).encode()
    resp = client.post("/api/logs/upload", files={"file": ("test.log", io.BytesIO(content), "text/plain")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["total_lines"] == 2
    assert data["parsed_lines"] == 2
    assert data["failed_lines"] == 0
    assert data["errors"] == []

def test_upload_partial_with_garbage(client: TestClient):
    lines = [
        json.dumps({"timestamp":"2026-10-20T10:15:04Z","severity":"ERROR","service":"auth-service","message":"ok"}),
        "not json at all",
        json.dumps({"timestamp":"2026-10-20T10:15:04Z","severity":"FATAL","service":"auth-service","message":"bad severity"}),
    ]
    content = "\n".join(lines).encode()
    resp = client.post("/api/logs/upload", files={"file": ("partial.log", io.BytesIO(content), "text/plain")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "partial"
    assert data["parsed_lines"] == 1
    assert data["failed_lines"] == 2
    assert len(data["errors"]) == 2
    # Line numbers preserved
    assert {e["line"] for e in data["errors"]} == {2,3}

def test_upload_empty_file_rejected(client: TestClient):
    resp = client.post("/api/logs/upload", files={"file": ("empty.log", io.BytesIO(b""), "text/plain")})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()

def test_upload_invalid_extension_rejected(client: TestClient):
    resp = client.post("/api/logs/upload", files={"file": ("bad.exe", io.BytesIO(b"{}"), "text/plain")})
    assert resp.status_code == 400
    assert "file type" in resp.json()["detail"].lower()

def test_upload_lifecycle_persists_and_searchable(client: TestClient, db_session):
    # Upload then immediately search via GET /api/logs
    lines = [
        json.dumps({"timestamp":"2026-10-20T12:00:00Z","severity":"INFO","service":"billing-service","request_id":"req-lifecycle","message":"lifecycle test"}),
    ]
    content = "\n".join(lines).encode()
    up = client.post("/api/logs/upload", files={"file": ("lifecycle.log", io.BytesIO(content), "text/plain")})
    assert up.status_code == 200
    # Search should find it
    resp = client.get("/api/logs?request_id=req-lifecycle")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert any(e["request_id"] == "req-lifecycle" for e in resp.json()["entries"])
