"""
Demo seeding for Log Search & Analyzer — shared by the CLI script and the
app's startup hook, so a fresh/ephemeral deployment always has data to show.

Why this exists: Render's filesystem is ephemeral and Free web services spin
down after 15 idle minutes, so a SQLite `logs.db` is wiped on every redeploy,
restart and spin-down. Seeding on startup (when empty) means the live demo and
the dashboard never open on an empty table.

Run manually:      python -m app.seed            (only if the DB is empty)
                   python -m app.seed --force    (insert another demo batch)
Legacy entry point: python seed_demo_data.py
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud import create_upload, bulk_create_log_entries
from app.models import LogEntry


def demo_dataset(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Realistic demo log set across services/severities, anchored to `now`.

    Timestamps are relative to the moment of seeding so "recent" filters and
    the demo's request-ID trace (`req-8f3k2`) always land inside the window a
    reviewer is looking at.
    """
    now = now or datetime.now(timezone.utc)
    m = lambda mins: now - timedelta(minutes=mins)  # noqa: E731 - terse helper

    return [
        # Authentication Service — the demo's traceable thread: req-8f3k1..3
        {"timestamp": m(45), "severity": "DEBUG", "service": "auth-service", "request_id": "req-8f3k1", "message": "Validating JWT signature header"},
        {"timestamp": m(44), "severity": "INFO", "service": "auth-service", "request_id": "req-8f3k1", "message": "User authentication successful for uid=1042"},
        {"timestamp": m(30), "severity": "WARN", "service": "auth-service", "request_id": "req-8f3k2", "message": "Session token near expiration (expires in 120s)"},
        {"timestamp": m(25), "severity": "ERROR", "service": "auth-service", "request_id": "req-8f3k2", "message": "Token refresh rejected: replay attack suspected"},
        {"timestamp": m(24), "severity": "CRITICAL", "service": "auth-service", "request_id": "req-8f3k3", "message": "Brute force threshold exceeded from IP 192.168.1.105"},
        # Payment & Billing Service
        {"timestamp": m(20), "severity": "INFO", "service": "billing-service", "request_id": "req-9a1b1", "message": "Processing invoice #INV-2026-901"},
        {"timestamp": m(18), "severity": "WARN", "service": "billing-service", "request_id": "req-9a1b1", "message": "Payment gateway latency elevated (1420ms)"},
        {"timestamp": m(15), "severity": "ERROR", "service": "billing-service", "request_id": "req-9a1b2", "message": "Charge declined: insufficient funds for customer cus_771"},
        {"timestamp": m(12), "severity": "CRITICAL", "service": "billing-service", "request_id": "req-9a1b3", "message": "Webhook receiver down: Stripe event delivery stalled"},
        # Gateway / Ingress — recurring error for the /api/stats/errors demo
        {"timestamp": m(10), "severity": "DEBUG", "service": "api-gateway", "request_id": "req-gw-01", "message": "TLS handshake completed (TLS 1.3)"},
        {"timestamp": m(8), "severity": "INFO", "service": "api-gateway", "request_id": "req-gw-02", "message": "GET /api/v1/health 200 OK 2ms"},
        {"timestamp": m(7), "severity": "ERROR", "service": "api-gateway", "request_id": "req-gw-05", "message": "502 Bad Gateway: Upstream service auth-service failed to respond in 4100ms"},
        {"timestamp": m(5), "severity": "WARN", "service": "api-gateway", "request_id": "req-gw-03", "message": "Rate limit warning: 85% capacity reached for client key clk_9"},
        {"timestamp": m(2), "severity": "ERROR", "service": "api-gateway", "request_id": "req-gw-04", "message": "502 Bad Gateway: Upstream service auth-service failed to respond in 5000ms"},
        # Background Tasks (nullable request_id — proves the column is optional)
        {"timestamp": m(50), "severity": "INFO", "service": "cron-scheduler", "request_id": None, "message": "Daily database vacuum and analyze completed in 320ms"},
        {"timestamp": m(35), "severity": "WARN", "service": "cache-cleaner", "request_id": None, "message": "Evicted 4,200 stale Redis keys; memory threshold reached 80%"},
        {"timestamp": m(1), "severity": "DEBUG", "service": "metrics-exporter", "request_id": None, "message": "Scraped 152 Prometheus metrics gauges"},
    ]


def count_entries(db: Session) -> int:
    return int(db.query(func.count(LogEntry.id)).scalar() or 0)


def seed_demo_data(db: Session, force: bool = False) -> int:
    """Insert the demo upload + entries. Idempotent unless `force=True`.

    Returns the number of entries inserted (0 when skipped).
    """
    if not force and count_entries(db) > 0:
        return 0

    entries = demo_dataset()
    upload = create_upload(
        db,
        filename="demo-seed.log",
        total_lines=len(entries),
        parsed_lines=len(entries),
        failed_lines=0,
        status="completed",
    )
    return bulk_create_log_entries(db, upload.id, entries)


def seed_demo_data_if_empty(db: Session) -> int:
    """Safe to call from app startup — seeds only when there is no data yet."""
    return seed_demo_data(db, force=False)


def main(argv: Optional[List[str]] = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    force = "--force" in argv

    # Imported lazily so `python -m app.seed --help` never touches the DB engine.
    from app.database import SessionLocal, init_db

    print("Initializing database schema...")
    init_db()

    db = SessionLocal()
    try:
        inserted = seed_demo_data(db, force=force)
        if inserted:
            print(f"Successfully seeded {inserted} demo log entries!")
        else:
            print("Database already has entries — nothing seeded (use --force to add anyway).")
        print(f"Total entries now: {count_entries(db)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
