# API Contract — Log Search & Analyzer

**Locked on Day 1 — all roles code against this.**

## Log Format (JSONL)
One JSON object per line:
```json
{
  "timestamp": "2026-10-20T10:15:04Z",
  "severity": "ERROR",
  "service": "auth-service",
  "request_id": "req-8f3k2",
  "message": "Database connection timeout"
}
```
- `timestamp`: ISO-8601 required
- `severity`: DEBUG, INFO, WARN, ERROR, CRITICAL (case-insensitive, stored uppercase)
- `service`: non-empty string required
- `request_id`: optional, null if missing
- `message`: non-empty string required
- Blank lines ignored, malformed lines skip-and-report with line numbers.

## Endpoints

### POST /api/logs/upload
Multipart field `file` (.log, .jsonl, .txt), max `MAX_UPLOAD_MB` env (default 5).
Returns 200 even with skipped lines, 400 on empty/oversized/bad type:
```json
{
  "upload_id": 7,
  "filename": "app.log",
  "status": "partial",
  "total_lines": 500,
  "parsed_lines": 487,
  "failed_lines": 13,
  "errors": [{ "line": 12, "reason": "unknown severity 'FATAL'" }]
}
```

### GET /api/logs?severity=&request_id=&from=&to=&page=&limit=
Filters: severity case-insensitive exact, request_id exact match, from/to ISO-8601 inclusive.
Pagination default limit 50, max 100, always paginated.
```json
{
  "total": 134,
  "page": 1,
  "limit": 50,
  "entries": [
    {
      "id": 12,
      "timestamp": "2026-10-20T10:15:04Z",
      "severity": "ERROR",
      "service": "auth-service",
      "request_id": "req-8f3k2",
      "message": "Database connection timeout"
    }
  ]
}
```

### GET /api/stats/errors?top=10
Groups ERROR/CRITICAL by normalized message (numbers/IDs replaced).
```json
{
  "errors": [
    {
      "message": "Database connection timeout",
      "severity": "ERROR",
      "count": 47,
      "first_seen": "2026-10-18T09:00:00Z",
      "last_seen": "2026-10-20T12:00:00Z",
      "sample_request_ids": ["req-8f3k2", "req-9aa11"]
    }
  ]
}
```

### GET /api/stats/summary
```json
{
  "total_entries": 12403,
  "by_severity": {"ERROR": 120, "INFO": 300},
  "by_service": {"auth-service": 200}
}
```

### GET /api/health
```json
{"status": "ok", "db": "ok", "total_entries": 12403, "last_upload": "2026-10-20T10:15:04Z"}
```
