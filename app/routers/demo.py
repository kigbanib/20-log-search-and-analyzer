"""Demo scenario endpoints for the Log Search & Analyzer.

Owner: QA & DevOps (Role 5) — demo tooling, not production logic.

These endpoints make the live demo *rehearsable*:
  POST /api/demo/scenario/incident — inject a scripted multi-service incident
  POST /api/demo/reset             — wipe and reseed the baseline dataset

They operate only on synthetic data. In a production deployment they would be
removed or behind auth — documented in README "Known limitations".
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import bulk_create_log_entries, create_upload
from app.database import get_db

router = APIRouter(prefix="/api/demo", tags=["Demo"])

HERO_REQUEST_ID = "req-inc7001"

_TIMEOUT = "Database connection timeout"
_502 = "Upstream service returned 502"


def _minutes_ago(n: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=n)


def _incident_entries() -> list[dict]:
    """A scripted incident spanning the last ~40 minutes.

    Story: a deploy goes out (t-14m), the DB connection pool saturates,
    errors cascade across services (t-11m → t-2m), one hero request
    (req-inc7001) traces the failure end-to-end, and the final entries are
    consecutive payment-service errors — so streak detection has a live fire
    to report.
    """

    def e(min_ago, severity, service, message, request_id=None):
        return {
            "timestamp": _minutes_ago(min_ago),
            "severity": severity,
            "service": service,
            "request_id": request_id,
            "message": message,
        }

    entries = [
        # ---- background noise before the incident ----
        e(38, "INFO", "api-gateway", "GET /api/v1/health 200 OK 2ms", "req-gw-88"),
        e(34, "INFO", "user-service", "User login successful", "req-u-311"),
        e(30, "DEBUG", "inventory-service", "Cache hit for key sku:9917"),
        e(26, "INFO", "billing-service", "Processing invoice #INV-2026-940", "req-b-207"),
        e(22, "WARN", "api-gateway", "Rate limit warning: 85% capacity reached", "req-gw-91"),
        e(19, "INFO", "auth-service", "User authentication successful for uid=2210", "req-a-415"),
        e(16, "DEBUG", "metrics-exporter", "Scraped 152 Prometheus metrics gauges"),
        # ---- the trigger ----
        e(14, "INFO", "api-gateway", "deploy v2.4.1 rolled out to payment-service", "req-inc-deploy"),
        e(13, "WARN", "payment-service", "Database connection pool at 90% capacity", "req-inc7000"),
        # ---- hero request: a checkout that walks into the fire (oldest → newest) ----
        e(12.5, "INFO", "api-gateway", "POST /api/checkout received", HERO_REQUEST_ID),
        e(12.2, "INFO", "payment-service", "Processing payment for order #7721", HERO_REQUEST_ID),
        e(11.8, "WARN", "payment-service", "Retrying upstream call (attempt 2)", HERO_REQUEST_ID),
        e(11.2, "ERROR", "auth-service", _TIMEOUT, HERO_REQUEST_ID),
        e(10.9, "ERROR", "payment-service", _TIMEOUT, HERO_REQUEST_ID),
        e(10.5, "ERROR", "api-gateway", _502, HERO_REQUEST_ID),
        # ---- the cascade ----
        e(10.1, "ERROR", "user-service", _TIMEOUT, "req-u-319"),
        e(9.6, "ERROR", "api-gateway", _502, "req-gw-97"),
        e(9.1, "ERROR", "auth-service", _TIMEOUT, "req-a-421"),
        e(8.6, "ERROR", "payment-service", "Failed to charge card: card declined", "req-b-211"),
        e(8.1, "WARN", "api-gateway", "Slow query detected (4.8s)", "req-gw-99"),
        e(7.6, "ERROR", "auth-service", _TIMEOUT, "req-a-422"),
        e(7.1, "ERROR", "payment-service", _TIMEOUT, "req-b-215"),
        e(6.6, "ERROR", "api-gateway", "Unhandled exception in request handler", "req-gw-102"),
        e(6.1, "ERROR", "inventory-service", _TIMEOUT, "req-i-140"),
        e(5.6, "ERROR", "payment-service", _TIMEOUT, "req-b-219"),
        e(5.1, "CRITICAL", "user-service", "Out of memory: worker killed", "req-u-325"),
        e(4.6, "ERROR", "payment-service", _TIMEOUT, "req-b-223"),
        e(4.1, "ERROR", "api-gateway", _502, "req-gw-104"),
        e(3.6, "ERROR", "payment-service", _TIMEOUT, "req-b-227"),
        e(3.1, "ERROR", "payment-service", _TIMEOUT, "req-b-231"),
        # ---- trailing consecutive streak (payment-service keeps failing) ----
        e(2.6, "ERROR", "payment-service", _TIMEOUT, "req-b-235"),
        e(2.1, "ERROR", "payment-service", _TIMEOUT, "req-b-239"),
        e(1.6, "ERROR", "payment-service", _TIMEOUT, "req-b-243"),
        e(1.1, "ERROR", "payment-service", _TIMEOUT, "req-b-247"),
        e(0.6, "ERROR", "payment-service", "Circuit breaker OPEN for db-primary", "req-b-251"),
    ]
    return entries


@router.post("/scenario/incident", summary="Inject a scripted incident dataset")
def trigger_incident(db: Session = Depends(get_db)):
    """Insert ~35 entries telling one cascading-failure story.

    Idempotent-safe to click repeatedly (entries simply accumulate). The
    response names the hero request ID so the UI can open its trace directly.
    """
    entries = _incident_entries()
    upload = create_upload(
        db,
        filename="scenario-incident.log",
        total_lines=len(entries),
        parsed_lines=len(entries),
        failed_lines=0,
        status="ok",
    )
    bulk_create_log_entries(db, upload.id, entries)
    return {
        "scenario": "incident",
        "inserted": len(entries),
        "hero_request_id": HERO_REQUEST_ID,
        "story": "deploy v2.4.1 → pool saturation → cascading Database connection timeouts",
    }


def _reset_and_reseed(db: Session) -> int:
    """Delete everything, then reseed the baseline dataset. Returns entries seeded."""
    import os

    from app.config import SEED_FILE
    from app.models import LogEntry, Upload
    from app.services.ingestion import process_upload

    db.query(LogEntry).delete()
    db.query(Upload).delete()
    db.commit()

    if os.path.exists(SEED_FILE):
        with open(SEED_FILE, "rb") as f:
            report = process_upload(f.read(), os.path.basename(SEED_FILE), db)
        return int(report["parsed_lines"])

    import seed_demo_data

    seed_demo_data.seed()
    return 16


@router.post("/reset", summary="Wipe and reseed the baseline demo dataset")
def reset_demo(db: Session = Depends(get_db)):
    """Restores the rehearsed baseline (testdata/sample_valid.jsonl when present)."""
    seeded = _reset_and_reseed(db)
    return {"reset": True, "seeded": seeded}
