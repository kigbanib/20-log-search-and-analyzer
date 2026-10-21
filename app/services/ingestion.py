"""Ingestion service: bridges the parser to SQLAlchemy storage.

Owner: Ingestion & Parser Lead (Role 1)
Collaborator: Search & Filter API Lead (Role 2) — uses `app.models` + `app.crud`

This is the DB-backed replacement for the early MVP `data.json` stand-in.
Policy: skip-and-report — one bad line never aborts the batch.
Blank lines are silently ignored (not counted as failed) to satisfy docs/log-format.md.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.crud import bulk_create_log_entries, create_upload
from app.parser.parser import parse_lines


def process_upload(file_bytes: bytes, filename: str, db: Session) -> dict[str, Any]:
    """Parse uploaded bytes, persist valid logs, return the API response dict.

    Returns exactly the contract from teamguide §6:
    {
        "upload_id": 7,
        "filename": "...",
        "status": "partial",
        "total_lines": 500,
        "parsed_lines": 487,
        "failed_lines": 13,
        "errors": [{"line": 12, "reason": "..."}]
    }
    """
    # 1. Decode bytes to text (utf-8 with replacement to avoid crashes on binary)
    text = file_bytes.decode("utf-8", errors="replace")
    lines = text.splitlines()

    # 2. Parse
    parsed, errors = parse_lines(lines)

    # 3. Filter blank-line errors: they are "ignored" per docs/log-format.md
    #    Parser reports them as ParseError(reason="empty line") so the caller can decide.
    #    We exclude them from failed count and error reporting, and from total.
    blank_errors = [e for e in errors if e.reason == "empty line"]
    real_errors = [e for e in errors if e.reason != "empty line"]

    total = len(lines) - len(blank_errors)
    # If file was only blanks, total becomes 0 — treat as empty-ish
    failed = len(real_errors)
    parsed_count = len(parsed)

    # 4. Determine status per spec
    if total == 0:
        # Empty file case already handled at route layer, but keep guard
        status = "failed"
    elif parsed_count == 0 and failed == 0:
        status = "failed"
    elif failed == 0:
        status = "ok"
    elif parsed_count > 0:
        status = "partial"
    else:
        status = "failed"  # all non-blank lines failed

    # 5. Persist to DB (create upload record + bulk insert log entries)
    upload = create_upload(
        db,
        filename=filename,
        total_lines=total,
        parsed_lines=parsed_count,
        failed_lines=failed,
        status=status,
    )

    if parsed:
        # Convert ParsedLog -> dict expected by crud.bulk_create_log_entries
        entries_data = [
            {
                "timestamp": log.timestamp,
                "severity": log.severity,
                "service": log.service,
                "request_id": log.request_id,
                "message": log.message,
            }
            for log in parsed
        ]
        bulk_create_log_entries(db, upload.id, entries_data)

    # 6. Build response matching brief's contract
    return {
        "upload_id": upload.id,
        "filename": filename,
        "status": status,
        "total_lines": total,
        "parsed_lines": parsed_count,
        "failed_lines": failed,
        "errors": [
            {"line": err.line_no, "reason": err.reason} for err in real_errors[:50]
        ],
    }
