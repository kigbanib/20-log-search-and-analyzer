"""
Unit tests for SQLAlchemy models (Upload, LogEntry).
Validates schema definitions, constraints, relationships, cascades, and indexes.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Upload, LogEntry


def test_upload_creation_defaults(db_session: Session):
    """Verify default values and column constraints on Upload model."""
    upload = Upload(filename="access.log")
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)

    assert upload.id is not None
    assert upload.filename == "access.log"
    assert upload.total_lines == 0
    assert upload.parsed_lines == 0
    assert upload.failed_lines == 0
    assert upload.status == "pending"
    assert isinstance(upload.uploaded_at, datetime)


def test_log_entry_creation_and_nullable_request_id(db_session: Session):
    """Verify LogEntry can be created with and without request_id."""
    upload = Upload(filename="system.log")
    db_session.add(upload)
    db_session.commit()

    entry_with_req = LogEntry(
        upload_id=upload.id,
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        service="worker",
        request_id="req-999",
        message="Job finished",
    )
    entry_without_req = LogEntry(
        upload_id=upload.id,
        timestamp=datetime.now(timezone.utc),
        severity="DEBUG",
        service="worker",
        request_id=None,
        message="Memory trace",
    )
    db_session.add_all([entry_with_req, entry_without_req])
    db_session.commit()

    assert entry_with_req.id is not None
    assert entry_with_req.request_id == "req-999"
    assert entry_without_req.id is not None
    assert entry_without_req.request_id is None


def test_relationship_upload_to_log_entries(db_session: Session):
    """Verify bidirectional relationship between Upload and LogEntry."""
    upload = Upload(filename="web.log")
    db_session.add(upload)
    db_session.commit()

    entry1 = LogEntry(
        upload_id=upload.id,
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        service="web",
        request_id="req-1",
        message="Request start",
    )
    entry2 = LogEntry(
        upload_id=upload.id,
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        service="web",
        request_id="req-1",
        message="Request end",
    )
    db_session.add_all([entry1, entry2])
    db_session.commit()
    db_session.refresh(upload)

    assert len(upload.entries) == 2
    assert upload.entries[0].message == "Request start"
    assert upload.entries[1].message == "Request end"
    assert entry1.upload.filename == "web.log"


def test_cascade_delete(db_session: Session):
    """Verify deleting an Upload cascades and removes its associated log entries."""
    upload = Upload(filename="temp.log")
    db_session.add(upload)
    db_session.commit()

    entry = LogEntry(
        upload_id=upload.id,
        timestamp=datetime.now(timezone.utc),
        severity="ERROR",
        service="api",
        message="Temporary error",
    )
    db_session.add(entry)
    db_session.commit()

    entry_id = entry.id
    db_session.delete(upload)
    db_session.commit()

    # Log entry should now be deleted
    assert db_session.get(LogEntry, entry_id) is None


def test_foreign_key_constraint_enforced(db_session: Session):
    """Verify that adding a LogEntry with a non-existent upload_id fails with IntegrityError."""
    orphan_entry = LogEntry(
        upload_id=99999,  # Does not exist
        timestamp=datetime.now(timezone.utc),
        severity="ERROR",
        service="api",
        message="Orphan log entry",
    )
    db_session.add(orphan_entry)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_not_null_constraints(db_session: Session):
    """Verify that omitting non-nullable fields (e.g. message, severity) fails."""
    upload = Upload(filename="app.log")
    db_session.add(upload)
    db_session.commit()

    # Missing message
    bad_entry = LogEntry(
        upload_id=upload.id,
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        service="api",
        message=None,  # Nullable is False
    )
    db_session.add(bad_entry)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_indexes_exist(db_session: Session):
    """Verify required indexes on log_entries: timestamp, severity, request_id."""
    inspector = inspect(db_session.bind)
    indexes = inspector.get_indexes("log_entries")
    indexed_columns = {idx["name"]: idx["column_names"] for idx in indexes}

    # Verify our required indexes are present
    assert "idx_log_entries_timestamp" in indexed_columns
    assert "timestamp" in indexed_columns["idx_log_entries_timestamp"]

    assert "idx_log_entries_severity" in indexed_columns
    assert "severity" in indexed_columns["idx_log_entries_severity"]

    assert "idx_log_entries_request_id" in indexed_columns
    assert "request_id" in indexed_columns["idx_log_entries_request_id"]
