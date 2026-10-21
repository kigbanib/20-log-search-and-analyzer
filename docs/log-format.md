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
```

## Validation rules (Role 1 enforces)

- `timestamp`: ISO-8601, required → else line is malformed
- `severity`: one of DEBUG, INFO, WARN, ERROR, CRITICAL (uppercase; parser uppercases input) → unknown value = malformed line
- `service`: non-empty string, required
- `request_id`: optional; missing or null → stored as null (and simply won't match request-ID searches)
- `message`: non-empty string, required

## Policy

- **Skip-and-report**: malformed lines become `ParseError` values with line numbers, never crash the batch.
- Blank/whitespace-only lines are ignored (not counted as errors).
- File size limit: `MAX_UPLOAD_MB` env (default 5 MB).
- Accepted extensions: `.log`, `.jsonl`, `.txt` (case-insensitive).

## Example (edge cases)

```jsonl
{"timestamp":"2026-10-20T10:15:04Z","severity":"error","service":"auth-service","request_id":"req-8f3k2","message":"Database connection timeout"}
{"timestamp":"2026-10-20T10:16:00Z","severity":"INFO","service":"cron-scheduler","message":"Daily vacuum completed"}
garbage line not json
{"timestamp":"2026-10-20T10:17:00Z","severity":"FATAL","service":"api-gateway","message":"unknown severity"}
```
Line 3 → `invalid JSON`, Line 4 → `unknown severity 'FATAL'`. Lines 1-2 parse (lowercase `error` normalized to `ERROR`, missing `request_id` → null).

