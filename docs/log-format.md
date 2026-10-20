# Log Format Specification

**Owner:** Ingestion & Parser Lead
**Status:** Locked on Day 1 — changes require sign-off from Search & Filter API Lead (Role 2)

## Accepted input

JSON Lines (`.jsonl` or `.log`), **one JSON object per line**. Blank lines are
ignored. Each non-blank line must be a JSON object with the fields below.

```json
{
  "timestamp": "2026-10-20T10:15:04Z",
  "severity": "ERROR",
  "service": "auth-service",
  "request_id": "req-8f3k2",
  "message": "Database connection timeout"
}