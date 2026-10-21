"""
Database access functions (CRUD) for Log Search & Analyzer.
Encapsulates all SQLAlchemy queries safely, avoiding raw SQL injection.
"""

from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import LogEntry, Upload


def get_logs(
    db: Session,
    severity: Optional[str] = None,
    request_id: Optional[str] = None,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    page: int = 1,
    limit: int = 50,
) -> Tuple[int, List[LogEntry]]:
    """
    Query log entries with filtering, exact count, predictable sorting, and pagination.

    Filters applied:
    - severity: Case-insensitive matching (e.g. 'error' matches 'ERROR').
    - request_id: Exact matching (partial matching strictly disallowed).
    - from_time: LogEntry.timestamp >= from_time
    - to_time: LogEntry.timestamp <= to_time

    Returns:
    - Tuple of (total_matching_count, list_of_log_entries)
    """
    filters = []

    # 1. Severity filter (case-insensitive)
    if severity is not None and severity.strip():
        normalized_severity = severity.strip().upper()
        # func.upper ensures case-insensitive matching at the database level
        filters.append(func.upper(LogEntry.severity) == normalized_severity)

    # 2. Request ID filter (exact match only, never LIKE/contains)
    if request_id is not None and request_id.strip():
        clean_request_id = request_id.strip()
        filters.append(LogEntry.request_id == clean_request_id)

    # 3. Date range filter (from_time)
    if from_time is not None:
        filters.append(LogEntry.timestamp >= from_time)

    # 4. Date range filter (to_time)
    if to_time is not None:
        filters.append(LogEntry.timestamp <= to_time)

    # Calculate total count of matching records BEFORE applying pagination
    count_statement = select(func.count(LogEntry.id)).where(*filters)
    total: int = db.scalar(count_statement) or 0

    # If total is 0, return early with an empty list
    if total == 0:
        return 0, []

    # Calculate pagination offset
    offset = (page - 1) * limit

    # Predictable ordering: most recent timestamp first, with id desc as deterministic tie-breaker
    entries_statement = (
        select(LogEntry)
        .where(*filters)
        .order_by(LogEntry.timestamp.desc(), LogEntry.id.desc())
        .offset(offset)
        .limit(limit)
    )

    entries = list(db.scalars(entries_statement).all())
    return total, entries


# ---------------------------------------------------------------------------
# Integration helpers for Role 1 (Ingestion & Parsing) & testing
# ---------------------------------------------------------------------------

def create_upload(
    db: Session,
    filename: str,
    total_lines: int = 0,
    parsed_lines: int = 0,
    failed_lines: int = 0,
    status: str = "pending",
) -> Upload:
    """Helper for Role 1 to record a log file upload."""
    upload = Upload(
        filename=filename,
        total_lines=total_lines,
        parsed_lines=parsed_lines,
        failed_lines=failed_lines,
        status=status,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return upload


def bulk_create_log_entries(
    db: Session,
    upload_id: int,
    entries_data: List[Dict[str, Any]],
) -> int:
    """
    Helper for Role 1 to bulk-insert parsed log entries.
    Expects entries_data items to have:
      - timestamp (datetime)
      - severity (str)
      - service (str)
      - request_id (Optional[str])
      - message (str)
    """
    entries = [
        LogEntry(
            upload_id=upload_id,
            timestamp=item["timestamp"],
            severity=item["severity"].upper(),  # normalize to uppercase upon ingestion
            service=item["service"],
            request_id=item.get("request_id"),
            message=item["message"],
        )
        for item in entries_data
    ]
    db.add_all(entries)
    db.commit()
    return len(entries)
