"""
Pytest configuration and test fixtures for Log Search & Analyzer.
Uses an isolated in-memory SQLite database with StaticPool for fast, deterministic testing.
"""

from datetime import datetime, timezone
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Upload, LogEntry

# In-memory SQLite with StaticPool ensures that all connections share the same in-memory database
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Enable foreign keys for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in type(dbapi_connection).__module__:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Creates a fresh database schema for each test function."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def seed_data(db_session: Session) -> dict:
    """
    Seeds a deterministic, comprehensive test dataset.
    Total entries: 15 log entries across 2 uploads.
    Covers:
      - All 5 severities: DEBUG, INFO, WARN, ERROR, CRITICAL
      - Exact request IDs: 'req-alpha', 'req-beta', 'req-gamma', 'req-alpha-child' (to test exact vs partial)
      - Nullable request_id (multiple entries with request_id = None)
      - Timestamps spanning 2026-10-18 to 2026-10-21
      - Multiple services: auth-service, payment-service, gateway, notification
    """
    upload1 = Upload(
        filename="server-access.log",
        uploaded_at=datetime(2026, 10, 18, 8, 0, 0, tzinfo=timezone.utc),
        total_lines=10,
        parsed_lines=10,
        failed_lines=0,
        status="completed",
    )
    upload2 = Upload(
        filename="auth-service.log",
        uploaded_at=datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc),
        total_lines=5,
        parsed_lines=5,
        failed_lines=0,
        status="completed",
    )
    db_session.add_all([upload1, upload2])
    db_session.commit()
    db_session.refresh(upload1)
    db_session.refresh(upload2)

    entries = [
        # --- Upload 1 entries (10 logs) ---
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 18, 9, 0, 0, tzinfo=timezone.utc),
            severity="DEBUG",
            service="gateway",
            request_id="req-alpha",
            message="Gateway initialized router",
        ),
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 18, 10, 15, 0, tzinfo=timezone.utc),
            severity="INFO",
            service="gateway",
            request_id="req-alpha",
            message="Incoming GET /login request received",
        ),
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 19, 11, 0, 0, tzinfo=timezone.utc),
            severity="WARN",
            service="auth-service",
            request_id="req-alpha",
            message="High latency on session lookup: 420ms",
        ),
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc),
            severity="ERROR",
            service="auth-service",
            request_id="req-beta",
            message="Failed login attempt for user user_42",
        ),
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 19, 13, 0, 0, tzinfo=timezone.utc),
            severity="ERROR",
            service="auth-service",
            request_id="req-beta",
            message="Password hashing salt mismatch",
        ),
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 20, 8, 30, 0, tzinfo=timezone.utc),
            severity="INFO",
            service="payment-service",
            request_id="req-gamma",
            message="Payment checkout initiated for invoice #9812",
        ),
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 20, 9, 0, 0, tzinfo=timezone.utc),
            severity="WARN",
            service="payment-service",
            request_id="req-gamma",
            message="Third-party payment gateway slow response: 1800ms",
        ),
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc),
            severity="CRITICAL",
            service="payment-service",
            request_id="req-gamma",
            message="Payment gateway circuit breaker tripped",
        ),
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 20, 11, 0, 0, tzinfo=timezone.utc),
            severity="INFO",
            service="notification",
            request_id=None,  # Nullable request ID
            message="Scheduled daily digest emails dispatched",
        ),
        LogEntry(
            upload_id=upload1.id,
            timestamp=datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc),
            severity="DEBUG",
            service="notification",
            request_id=None,  # Nullable request ID
            message="Flushed 142 notification worker buffers",
        ),

        # --- Upload 2 entries (5 logs) ---
        LogEntry(
            upload_id=upload2.id,
            timestamp=datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc),
            severity="INFO",
            service="auth-service",
            request_id="req-alpha-child",  # Contains 'req-alpha' as substring!
            message="Token refreshed for background process",
        ),
        LogEntry(
            upload_id=upload2.id,
            timestamp=datetime(2026, 10, 20, 15, 0, 0, tzinfo=timezone.utc),
            severity="WARN",
            service="auth-service",
            request_id=None,  # Nullable
            message="Deprecation warning: OAuth v1 header received",
        ),
        LogEntry(
            upload_id=upload2.id,
            timestamp=datetime(2026, 10, 20, 16, 0, 0, tzinfo=timezone.utc),
            severity="ERROR",
            service="payment-service",
            request_id="req-delta",
            message="Stripe webhook signature validation failed",
        ),
        LogEntry(
            upload_id=upload2.id,
            timestamp=datetime(2026, 10, 21, 1, 0, 0, tzinfo=timezone.utc),
            severity="ERROR",
            service="gateway",
            request_id="req-delta",
            message="Upstream gateway timeout on /checkout endpoint",
        ),
        LogEntry(
            upload_id=upload2.id,
            timestamp=datetime(2026, 10, 21, 2, 0, 0, tzinfo=timezone.utc),
            severity="CRITICAL",
            service="gateway",
            request_id="req-epsilon",
            message="Primary database connection pool exhausted",
        ),
    ]

    db_session.add_all(entries)
    db_session.commit()

    return {
        "upload1": upload1,
        "upload2": upload2,
        "total_entries": len(entries),  # 15
        "entries": entries,
    }
