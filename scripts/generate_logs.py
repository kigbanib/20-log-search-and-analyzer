"""
Generate realistic JSONL log datasets for Log Search & Analyzer.

Owner: Role 5 — Test Data, QA & DevOps Lead (per teamguide §5 Day 1 deliverable)
Produces:
- Multiple days of timestamps
- 4-6 services
- Recurring error messages (so stats panel has something to show)
- Some lines with no request_id
- Edge-case datasets requested by rubric

Usage:
  python scripts/generate_logs.py               # -> testdata/sample_valid.jsonl (500 lines)
  python scripts/generate_logs.py --all         # -> all edge-case files in testdata/
  python scripts/generate_logs.py --seed logs.db # also seeds SQLite via seed_demo_data logic
"""

import argparse
import json
import random
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVICES = ["auth-service", "payment-service", "api-gateway", "user-service", "inventory-service", "billing-service"]
SEVERITIES = ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"]
# Weighted pool matches production (~60% INFO/WARN, 20% ERROR/CRITICAL)
SEVERITY_POOL = ["DEBUG","DEBUG", "INFO","INFO","INFO","INFO", "WARN","WARN", "ERROR","ERROR", "CRITICAL"]

MESSAGES = {
    "DEBUG": ["Entering processOrder()", "SQL query executed in 12ms", "Cache hit for key user:42", "TLS handshake completed (TLS 1.3)"],
    "INFO": ["Request completed", "User login successful", "Health check passed", "Cache warmed", "Processing invoice #INV-2026-901", "GET /api/v1/health 200 OK 2ms"],
    "WARN": ["Slow query detected (2.3s)", "Retrying upstream call (attempt 2)", "Deprecated API version used by client", "Rate limit warning: 85% capacity reached", "Session token near expiration (expires in 120s)"],
    "ERROR": ["Database connection timeout", "Failed to charge card: card declined", "Unhandled exception in request handler", "Upstream service returned 502", "Token refresh rejected: replay attack suspected"],
    "CRITICAL": ["Out of memory: worker killed", "Disk quota exceeded on volume /data", "Brute force threshold exceeded from IP 192.168.1.105", "Webhook receiver down: Stripe event delivery stalled"],
}

def random_request_id():
    # 25% null (cron, gc)
    if random.random() < 0.25:
        return None
    return f"req-{random.randint(0, 0xffffff):06x}"

def make_entry(ts: datetime, severity: str = None, service: str = None, request_id=None, message=None):
    sev = severity or random.choice(SEVERITY_POOL)
    svc = service or random.choice(SERVICES)
    # Recurring error bias: 40% of ERRORs reuse the same 2 messages to make stats meaningful
    if sev in ("ERROR","CRITICAL") and random.random() < 0.4:
        msg = random.choice(["Database connection timeout", "Database connection timeout", "Upstream service returned 502"])
    else:
        msg = message or random.choice(MESSAGES[sev])
    rid = request_id if request_id is not None else random_request_id()
    obj = {
        "timestamp": ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "severity": sev,
        "service": svc,
        "message": msg,
    }
    if rid is not None:
        obj["request_id"] = rid
    return obj

def generate_valid(path: Path, n=500, days=3):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    entries = []
    for i in range(n):
        # Spread timestamps across days + ensure some share request_id for tracing
        ts = start + timedelta(seconds=random.randint(0, days*86400))
        # Force a traceable request: every 20th entry shares req-8f3k2
        if i % 50 == 0:
            entries.append(make_entry(ts, service="auth-service", severity=random.choice(SEVERITIES), request_id="req-8f3k2"))
        else:
            entries.append(make_entry(ts))
    # Sort by timestamp for readability
    entries.sort(key=lambda x: x["timestamp"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    print(f"Wrote {n} entries to {path}")

def generate_malformed(path: Path, n=100, garbage_ratio=0.3):
    now = datetime.now(timezone.utc)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for i in range(n):
            if random.random() < garbage_ratio:
                # 30% garbage
                f.write(random.choice([
                    "this is not json\n",
                    "{broken json\n",
                    json.dumps({"severity":"INFO","service":"auth-service","message":"missing timestamp"}) + "\n",
                    json.dumps({"timestamp":"2026-10-20T10:00:00Z","severity":"FATAL","service":"auth-service","message":"unknown severity"}) + "\n",
                    "\n",  # blank line
                ]))
            else:
                ts = now - timedelta(minutes=random.randint(0, 1000))
                f.write(json.dumps(make_entry(ts)) + "\n")
    print(f"Wrote {n} lines ({garbage_ratio*100:.0f}% garbage) to {path}")

def generate_unknown_severities(path: Path, n=20):
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    bad_sevs = ["FATAL", "TRACE", "NOTICE", "fatal", "trace"]
    with open(path, "w") as f:
        for i in range(n):
            sev = random.choice(bad_sevs)
            f.write(json.dumps({
                "timestamp": now.isoformat().replace("+00:00","Z"),
                "severity": sev,
                "service": "auth-service",
                "request_id": f"req-bad-{i}",
                "message": "This has unknown severity"
            }) + "\n")
    print(f"Wrote {n} unknown-severity lines to {path}")

def generate_empty(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    open(path, "w").close()
    print(f"Wrote empty file to {path}")

def generate_oversized(path: Path, target_mb=6):
    # Create ~6MB file (over 5MB limit) for failure path test
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    target_bytes = target_mb * 1024 * 1024
    written = 0
    with open(path, "w") as f:
        while written < target_bytes:
            line = json.dumps(make_entry(now)) + "\n"
            f.write(line)
            written += len(line.encode())
    print(f"Wrote oversized {target_mb}MB file to {path} ({written} bytes)")

def generate_fake_image_renamed(path: Path):
    # Non-log file renamed to .log (binary-ish content)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + os.urandom(1024))
    print(f"Wrote fake image renamed to {path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate log datasets")
    parser.add_argument("--output", default="testdata/sample_valid.jsonl", help="Output path for valid dataset")
    parser.add_argument("--count", type=int, default=500, help="Number of entries for valid dataset")
    parser.add_argument("--all", action="store_true", help="Generate all edge-case datasets")
    args = parser.parse_args()

    random.seed(42)

    # Always generate valid sample
    generate_valid(Path(args.output), n=args.count)

    if args.all:
        generate_empty(Path("testdata/empty.log"))
        generate_malformed(Path("testdata/malformed_30pct.jsonl"), n=100, garbage_ratio=0.3)
        generate_malformed(Path("testdata/malformed_30pct.log"), n=200, garbage_ratio=0.3)
        generate_unknown_severities(Path("testdata/unknown_severities.log"))
        generate_oversized(Path("testdata/oversized.log"), target_mb=6)
        generate_fake_image_renamed(Path("testdata/fake_image.log"))
        # Also a small valid for API happy path
        generate_valid(Path("testdata/sample_5.log"), n=5)
        print("\nAll testdata generated in testdata/")
