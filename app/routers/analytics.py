"""Role 3: analytics and monitoring endpoints for the Log Search & Analyzer.

Owner: Analytics & Reporting Lead (Role 3) — recurring errors + monitoring
Integration assumptions from the team guide:
- SQLAlchemy models: LogEntry(id, timestamp, severity, service, request_id, message)
- Upload(id, uploaded_at, ...)

Mount with: app.include_router(router)
"""

from datetime import datetime, timedelta, timezone
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_owner, visible_entries, visible_uploads
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
    """ISO-8601 with explicit 'Z' for naive datetimes (SQLite stores naive UTC)."""
    if value is None:
        return None
    return value.isoformat() if value.tzinfo else value.isoformat() + "Z"


@router.get("/stats/errors", summary="Top recurring ERROR/CRITICAL patterns")
def recurring_errors(
    top: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    owner: str = Depends(get_owner),
):
    """Return the most common ERROR/CRITICAL patterns and example request IDs.
    Session-scoped: only the caller's rows + the shared anonymous bucket."""
    rows = (
        db.query(LogEntry)
        .filter(func.upper(LogEntry.severity).in_(["ERROR", "CRITICAL"]))
        .filter(visible_entries(owner))
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
def stats_summary(db: Session = Depends(get_db), owner: str = Depends(get_owner)):
    """Return entry totals grouped by severity and service (session-scoped)."""
    severity_rows = (
        db.query(LogEntry.severity, func.count(LogEntry.id))
        .filter(visible_entries(owner))
        .group_by(LogEntry.severity)
        .all()
    )
    service_rows = (
        db.query(LogEntry.service, func.count(LogEntry.id))
        .filter(visible_entries(owner))
        .group_by(LogEntry.service)
        .order_by(func.count(LogEntry.id).desc())
        .all()
    )
    return {
        "total_entries": sum(int(count) for _, count in severity_rows),
        "by_severity": {str(name).upper(): int(count) for name, count in severity_rows},
        "by_service": {str(name): int(count) for name, count in service_rows},
    }


# Fixed key order kept stable for chart rendering on the dashboard.
SEVERITY_ORDER = ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"]

# bucket name -> (SQLite strftime pattern, max buckets returned)
_TIMELINE_BUCKETS = {
    "hour": ("%Y-%m-%dT%H:00:00", 72),
    "day": ("%Y-%m-%d", 60),
}


@router.get("/stats/timeline", summary="Log volume per severity over time")
def stats_timeline(
    bucket: str = Query("hour", pattern="^(hour|day)$"),
    db: Session = Depends(get_db),
    owner: str = Depends(get_owner),
):
    """Counts per severity grouped into time buckets, zero-filled.

    Designed for the dashboard activity chart: every bucket contains all five
    severity keys (0 when absent) so the frontend can stack bars directly.
    Grouping happens in SQL (strftime), not in Python memory.
    Session-scoped: only the caller's rows + the shared anonymous bucket.
    """
    fmt, max_buckets = _TIMELINE_BUCKETS[bucket]

    bounds = (
        db.query(func.min(LogEntry.timestamp), func.max(LogEntry.timestamp))
        .filter(visible_entries(owner))
        .one()
    )
    if not bounds[0] or not bounds[1]:
        return {"bucket": bucket, "buckets": []}

    rows = (
        db.query(
            func.strftime(fmt, LogEntry.timestamp).label("b"),
            LogEntry.severity,
            func.count(LogEntry.id),
        )
        .filter(visible_entries(owner))
        .group_by("b", LogEntry.severity)
        .all()
    )

    counts: dict = {}
    for b, sev, c in rows:
        counts.setdefault(b, {s: 0 for s in SEVERITY_ORDER})
        counts[b][str(sev).upper()] = int(c)

    ordered = sorted(counts)
    if len(ordered) > max_buckets:  # cap to the most recent window
        ordered = ordered[-max_buckets:]

    # Zero-fill the range so chart columns have no gaps.
    buckets = []
    if ordered:
        step = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)
        cur = datetime.strptime(ordered[0], fmt)
        end_key = ordered[-1]
        while True:
            key = cur.strftime(fmt)
            buckets.append({
                "start": key + ("Z" if bucket == "hour" else ""),
                **counts.get(key, {s: 0 for s in SEVERITY_ORDER}),
            })
            if key == end_key:
                break
            cur += step
    return {"bucket": bucket, "buckets": buckets}


# Severity levels counted when detecting failure streaks.
BAD_SEVERITIES = {"ERROR", "CRITICAL"}


@router.get("/stats/streaks", summary="Per-service trailing error streaks")
def error_streaks(
    min_streak: int = Query(3, ge=2, le=50, alias="min"),
    db: Session = Depends(get_db),
    owner: str = Depends(get_owner),
):
    """Detect services whose most recent entries are ALL errors.

    A streak = consecutive ERROR/CRITICAL entries at the tail of a service's
    own log stream (ordered by timestamp desc, id desc as tie-breaker).
    Answers "what is failing *right now, back-to-back*?" — a sequence signal,
    complementary to /stats/errors which answers "what fails *often*?"

    MVP trade-off: single ordered query + in-memory scan (same pattern as
    /stats/errors). Scale path: SQL window functions (LAG) per service.
    """
    rows = (
        db.query(
            LogEntry.service,
            LogEntry.severity,
            LogEntry.timestamp,
            LogEntry.message,
            LogEntry.request_id,
        )
        .filter(visible_entries(owner))
        .order_by(LogEntry.service, LogEntry.timestamp.desc(), LogEntry.id.desc())
        .all()
    )

    streaks = []
    current = None
    for service, severity, ts, message, rid in rows:
        if current is None or current["service"] != service:
            if current is not None and current["streak"] >= min_streak:
                streaks.append(current)
            # New service stream: open a fresh streak counter.
            current = {
                "service": service,
                "streak": 0,
                "since": None,
                "last_seen": None,
                "last_message": None,
                "sample_request_ids": set(),
                "_open": True,
            }
        if not current["_open"]:
            continue
        if str(severity).upper() in BAD_SEVERITIES:
            if current["streak"] == 0:  # newest entry of the streak
                current["last_seen"] = ts
                current["last_message"] = (message or "").strip()
            current["streak"] += 1
            current["since"] = ts  # keeps walking back to the oldest entry
            if rid and len(current["sample_request_ids"]) < 3:
                current["sample_request_ids"].add(rid)
        else:
            current["_open"] = False  # first non-error entry closes the streak
    if current is not None and current["streak"] >= min_streak:
        streaks.append(current)

    for s in streaks:
        s["sample_request_ids"] = sorted(s["sample_request_ids"])
        s["since"] = _iso(s["since"])
        s["last_seen"] = _iso(s["last_seen"])
        del s["_open"]
    streaks.sort(key=lambda s: (-s["streak"], s["service"]))
    return {"min_streak": min_streak, "streaks": streaks}


@router.get("/health", summary="Service health check")
def health(db: Session = Depends(get_db), owner: str = Depends(get_owner)):
    """Lightweight readiness check: app responds and database can be queried.

    Returns superset of teamguide + Role 2 expectations so both test suites pass.
    `total_entries` / `last_upload` are session-scoped so the dashboard pill
    shows each visitor THEIR count, never everyone else's uploads.
    """
    try:
        total = (
            db.query(func.count(LogEntry.id))
            .filter(visible_entries(owner))
            .scalar()
            or 0
        )
        last_upload = (
            db.query(func.max(Upload.uploaded_at))
            .filter(visible_uploads(owner))
            .scalar()
        )
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
