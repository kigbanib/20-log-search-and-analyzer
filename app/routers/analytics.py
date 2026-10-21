"""Role 3: analytics and monitoring endpoints for the Log Search & Analyzer.

Owner: Analytics & Reporting Lead (Role 3) — recurring errors + monitoring
Integration assumptions from the team guide:
- SQLAlchemy models: LogEntry(id, timestamp, severity, service, request_id, message)
- Upload(id, uploaded_at, ...)

Mount with: app.include_router(router)
"""

from datetime import datetime, timezone
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogEntry, Upload

router = APIRouter(prefix="/api", tags=["Analytics & Monitoring"])


def normalize_message(message: str) -> str:
    """Replace variable numbers/IDs with a common token so similar errors group.

    Examples: 'timeout after 5023ms' -> 'timeout after <value>ms';
    'worker 1842 failed' -> 'worker <value> failed'.
    Keep the original message in the database; normalize only for reporting.
    """
    text = (message or "").strip().lower()
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<id>", text, flags=re.I)
    text = re.sub(r"\b(?:req[-_]?)?[0-9a-f]{6,}\b", "<id>", text, flags=re.I)
    text = re.sub(r"\d+(?:\.\d+)?", "<value>", text)
    return re.sub(r"\s+", " ", text)


def _iso(value: Optional[datetime]):
    return value.isoformat() if value else None


@router.get("/stats/errors", summary="Top recurring ERROR/CRITICAL patterns")
def recurring_errors(top: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    """Return the most common ERROR/CRITICAL patterns and example request IDs."""
    rows = (
        db.query(LogEntry)
        .filter(func.upper(LogEntry.severity).in_(["ERROR", "CRITICAL"]))
        .order_by(LogEntry.timestamp.asc(), LogEntry.id.asc())
        .all()
    )
    groups = {}
    for row in rows:
        key = normalize_message(row.message)
        if key not in groups:
            groups[key] = {
                "message": row.message.strip(),
                "count": 0,
                "first_seen": row.timestamp,
                "last_seen": row.timestamp,
                "sample_request_ids": [],
                "_requests": set(),
                "severity": row.severity.upper(),
            }
        item = groups[key]
        item["count"] += 1
        item["first_seen"] = min(item["first_seen"], row.timestamp)
        item["last_seen"] = max(item["last_seen"], row.timestamp)
        # Prefer a representative CRITICAL label if both severities share a pattern.
        if row.severity.upper() == "CRITICAL":
            item["severity"] = "CRITICAL"
        rid = row.request_id
        if rid and rid not in item["_requests"] and len(item["sample_request_ids"]) < 5:
            item["sample_request_ids"].append(rid)
            item["_requests"].add(rid)
    result = sorted(groups.values(), key=lambda x: (-x["count"], x["message"].lower()))[
        :top
    ]
    for item in result:
        item.pop("_requests")
        item["first_seen"] = _iso(item["first_seen"])
        item["last_seen"] = _iso(item["last_seen"])
    return {"errors": result}


@router.get("/stats/summary", summary="Totals per severity and service")
def stats_summary(db: Session = Depends(get_db)):
    """Return entry totals grouped by severity and service."""
    severity_rows = (
        db.query(LogEntry.severity, func.count(LogEntry.id))
        .group_by(LogEntry.severity)
        .all()
    )
    service_rows = (
        db.query(LogEntry.service, func.count(LogEntry.id))
        .group_by(LogEntry.service)
        .order_by(func.count(LogEntry.id).desc())
        .all()
    )
    return {
        "total_entries": sum(int(count) for _, count in severity_rows),
        "by_severity": {str(name).upper(): int(count) for name, count in severity_rows},
        "by_service": {str(name): int(count) for name, count in service_rows},
    }


@router.get("/health", summary="Service health check")
def health(db: Session = Depends(get_db)):
    """Lightweight readiness check: app responds and database can be queried.
    
    Returns superset of teamguide + Role 2 expectations so both test suites pass.
    """
    try:
        total = db.query(func.count(LogEntry.id)).scalar() or 0
        last_upload = db.query(func.max(Upload.uploaded_at)).scalar()
        return {
            "status": "ok",
            "db": "ok",
            "total_entries": int(total),
            "last_upload": _iso(last_upload),
            # Role 2 / deployment expectation
            "service": "Log Search & Analyzer",
            "version": "1.0.0",
        }
    except Exception:
        # Do not expose database exception details or credentials to clients.
        return {
            "status": "degraded",
            "db": "error",
            "total_entries": None,
            "last_upload": None,
            "service": "Log Search & Analyzer",
            "version": "1.0.0",
        }
