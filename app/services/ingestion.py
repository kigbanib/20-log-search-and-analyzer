"""Ingestion service: bridges the parser to storage.

For the MVP (before Role 2's DB is ready), we persist to a local JSON file.
When models.py lands, we swap `_save_to_disk()` for a SQLAlchemy insert.
"""

import json
import os
from typing import Any

from app.parser.parser import parse_lines
from app.parser.schema import ParseError, ParsedLog

DATA_FILE = "data.json"


def _load_existing() -> list[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _serialize_log(log: ParsedLog) -> dict:
    return {
        "timestamp": log.timestamp.isoformat(),
        "severity": log.severity,
        "service": log.service,
        "request_id": log.request_id,
        "message": log.message,
    }


def process_upload(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Parse uploaded bytes, save valid logs, return the API response dict."""
    # 1. Decode bytes to text (utf-8 with replacement to avoid crashes on binary)
    text = file_bytes.decode("utf-8", errors="replace")
    lines = text.splitlines()

    # 2. Parse
    parsed, errors = parse_lines(lines)

    # 3. Determine status
    total = len(lines)
    failed = len(errors)
    parsed_count = len(parsed)

    if parsed_count == 0 and failed == 0:
        status = "failed"  # empty file
    elif failed == 0:
        status = "ok"
    elif parsed_count > 0:
        status = "partial"
    else:
        status = "failed"  # all lines failed

    # 4. Save valid logs to disk (MVP stand-in for DB)
    if parsed:
        existing = _load_existing()
        existing.extend(_serialize_log(log) for log in parsed)
        with open(DATA_FILE, "w") as f:
            json.dump(existing, f, indent=2)

    # 5. Build the response (exactly matching the brief's contract)
    return {
        "upload_id": 1,  # hardcoded for MVP, will be DB-assigned later
        "filename": filename,
        "status": status,
        "total_lines": total,
        "parsed_lines": parsed_count,
        "failed_lines": failed,
        "errors": [
            {"line": err.line_no, "reason": err.reason} for err in errors[:50]
        ],  # Cap at 50 error details to keep response small
    }