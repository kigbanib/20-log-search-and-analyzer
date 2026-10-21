"""
SQLAlchemy ORM models for Log Search & Analyzer.
Defines 'uploads' and 'log_entries' tables with indexes and relationships.
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now() -> datetime:
    """Helper to return current UTC datetime."""
    return datetime.now(timezone.utc)


class Upload(Base):
    """
    Tracks uploaded log files and their parsing ingestion status.
    Shared contract with Role 1 (Ingestion & Parsing Lead).
    """
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    total_lines = Column(Integer, nullable=False, default=0)
    parsed_lines = Column(Integer, nullable=False, default=0)
    failed_lines = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="pending")

    # Relationship to log entries (with cascade delete)
    entries = relationship(
        "LogEntry",
        back_populates="upload",
        cascade="all, delete-orphan",
        order_by="LogEntry.id",
    )

    def __repr__(self) -> str:
        return (
            f"<Upload(id={self.id}, filename='{self.filename}', "
            f"status='{self.status}', total={self.total_lines})>"
        )


class LogEntry(Base):
    """
    Stores individual parsed log events.
    Owned by Role 2, queried by Role 3 (Analytics) and Role 4 (Dashboard).
    """
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    upload_id = Column(
        Integer,
        ForeignKey("uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    service = Column(String(100), nullable=False)
    request_id = Column(String(100), nullable=True, index=True)
    message = Column(Text, nullable=False)

    # Relationship back to the parent Upload
    upload = relationship("Upload", back_populates="entries")

    # Explicit indexes as required by the specification:
    # 1. timestamp: for fast date-range filtering and sorting
    # 2. severity: for fast severity filtering
    # 3. request_id: for fast exact request-ID trace lookups
    # 4. composite (timestamp, severity): for multi-filter queries
    __table_args__ = (
        Index("idx_log_entries_timestamp", "timestamp"),
        Index("idx_log_entries_severity", "severity"),
        Index("idx_log_entries_request_id", "request_id"),
        Index("idx_log_entries_ts_severity", "timestamp", "severity"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogEntry(id={self.id}, severity='{self.severity}', "
            f"service='{self.service}', req_id='{self.request_id}', "
            f"ts='{self.timestamp}')>"
        )

    def to_dict(self) -> dict:
        """Utility for easy serialization or debugging."""
        return {
            "id": self.id,
            "upload_id": self.upload_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "severity": self.severity,
            "service": self.service,
            "request_id": self.request_id,
            "message": self.message,
        }
