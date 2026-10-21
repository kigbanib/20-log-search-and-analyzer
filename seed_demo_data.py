"""
Seed script to populate a local development SQLite database (logs.db)
with realistic test log data across multiple services, severities, and timestamps.
Run with: python3 seed_demo_data.py
"""

from datetime import datetime, timedelta, timezone
from app.database import init_db, SessionLocal
from app.crud import create_upload, bulk_create_log_entries

def seed():
    print("Initializing database schema...")
    init_db()

    db = SessionLocal()
    try:
        print("Creating mock uploads...")
        up1 = create_upload(db, filename="production-api.log", total_lines=20, parsed_lines=20, failed_lines=0, status="completed")
        up2 = create_upload(db, filename="billing-worker.log", total_lines=10, parsed_lines=10, failed_lines=0, status="completed")

        now = datetime.now(timezone.utc)

        sample_entries = [
            # Authentication Service
            {"timestamp": now - timedelta(minutes=45), "severity": "DEBUG", "service": "auth-service", "request_id": "req-8f3k1", "message": "Validating JWT signature header"},
            {"timestamp": now - timedelta(minutes=44), "severity": "INFO", "service": "auth-service", "request_id": "req-8f3k1", "message": "User authentication successful for uid=1042"},
            {"timestamp": now - timedelta(minutes=30), "severity": "WARN", "service": "auth-service", "request_id": "req-8f3k2", "message": "Session token near expiration (expires in 120s)"},
            {"timestamp": now - timedelta(minutes=25), "severity": "ERROR", "service": "auth-service", "request_id": "req-8f3k2", "message": "Token refresh rejected: replay attack suspected"},
            {"timestamp": now - timedelta(minutes=24), "severity": "CRITICAL", "service": "auth-service", "request_id": "req-8f3k3", "message": "Brute force threshold exceeded from IP 192.168.1.105"},

            # Payment & Billing Service
            {"timestamp": now - timedelta(minutes=20), "severity": "INFO", "service": "billing-service", "request_id": "req-9a1b1", "message": "Processing invoice #INV-2026-901"},
            {"timestamp": now - timedelta(minutes=18), "severity": "WARN", "service": "billing-service", "request_id": "req-9a1b1", "message": "Payment gateway latency elevated (1420ms)"},
            {"timestamp": now - timedelta(minutes=15), "severity": "ERROR", "service": "billing-service", "request_id": "req-9a1b2", "message": "Charge declined: insufficient funds for customer cus_771"},
            {"timestamp": now - timedelta(minutes=12), "severity": "CRITICAL", "service": "billing-service", "request_id": "req-9a1b3", "message": "Webhook receiver down: Stripe event delivery stalled"},

            # Gateway / Ingress
            {"timestamp": now - timedelta(minutes=10), "severity": "DEBUG", "service": "api-gateway", "request_id": "req-gw-01", "message": "TLS handshake completed (TLS 1.3)"},
            {"timestamp": now - timedelta(minutes=8), "severity": "INFO", "service": "api-gateway", "request_id": "req-gw-02", "message": "GET /api/v1/health 200 OK 2ms"},
            {"timestamp": now - timedelta(minutes=5), "severity": "WARN", "service": "api-gateway", "request_id": "req-gw-03", "message": "Rate limit warning: 85% capacity reached for client key clk_9"},
            {"timestamp": now - timedelta(minutes=2), "severity": "ERROR", "service": "api-gateway", "request_id": "req-gw-04", "message": "502 Bad Gateway: Upstream service auth-service failed to respond in 5000ms"},

            # Background Tasks (Nullable request_id)
            {"timestamp": now - timedelta(minutes=50), "severity": "INFO", "service": "cron-scheduler", "request_id": None, "message": "Daily database vacuum and analyze completed in 320ms"},
            {"timestamp": now - timedelta(minutes=35), "severity": "WARN", "service": "cache-cleaner", "request_id": None, "message": "Evicted 4,200 stale Redis keys; memory threshold reached 80%"},
            {"timestamp": now - timedelta(minutes=1), "severity": "DEBUG", "service": "metrics-exporter", "request_id": None, "message": "Scraped 152 Prometheus metrics gauges"},
        ]

        inserted = bulk_create_log_entries(db, up1.id, sample_entries)
        print(f"Successfully seeded {inserted} log entries across uploads {up1.id} and {up2.id}!")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
