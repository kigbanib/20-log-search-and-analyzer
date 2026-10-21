# Role 2: Search & Filter API Lead — Documentation
**Project:** Log Search & Analyzer (Mini Datadog / Splunk)
**Lead:** Role 2 (Search & Filter API Lead)
**Framework:** FastAPI + SQLAlchemy + SQLite (PostgreSQL-compatible)

---

## 1. Executive Summary & Responsibilities

As **Role 2 Lead**, I own:
1. The **database schema** (`uploads` and `log_entries` tables).
2. The **database indexes** (`timestamp`, `severity`, `request_id`).
3. The **Search & Filter API endpoint** (`GET /api/logs`) and its full contract.
4. **Input validation**, **case-insensitive severity filtering**, **exact request ID matching**, and **date-range filtering**.
5. **Deterministic ordering** and **pre-pagination total record counts**.
6. **Cross-role integration interfaces** for Role 1 (Ingestion), Role 3 (Analytics), Role 4 (Dashboard), and Role 5 (QA/Deployment).

---

## 2. Database Schema & Architecture

The database architecture is designed with a normalized relational model separating upload metadata from individual high-velocity log entries.

```
+------------------------------------+          +--------------------------------------------+
|             uploads                |          |                log_entries                 |
+------------------------------------+          +--------------------------------------------+
| id: Integer (PK, AutoIncrement)    |<--------+| id: Integer (PK, AutoIncrement)            |
| filename: String(255)              |   1:N    | upload_id: Integer (FK -> uploads.id)      |
| uploaded_at: DateTime(tz=True)     |          | timestamp: DateTime(tz=True) (INDEXED)     |
| total_lines: Integer (default 0)   |          | severity: String(20) (INDEXED)             |
| parsed_lines: Integer (default 0)  |          | service: String(100)                       |
| failed_lines: Integer (default 0)  |          | request_id: String(100, Nullable) (INDEXED)|
| status: String(50)                 |          | message: Text                              |
+------------------------------------+          +--------------------------------------------+
```

### Table 1: `uploads`
Tracks ingestion batches uploaded by users.
- `id`: Primary key.
- `filename`: Name of the uploaded log file.
- `uploaded_at`: UTC timestamp of the upload.
- `total_lines`: Number of lines detected in the raw log file.
- `parsed_lines`: Successfully structured log lines.
- `failed_lines`: Corrupted or unparseable lines.
- `status`: Lifecycle state (`pending`, `completed`, `failed`).

### Table 2: `log_entries`
Stores structured log events extracted by Role 1.
- `id`: Primary key.
- `upload_id`: Foreign key referencing `uploads.id` with `ON DELETE CASCADE`. If an upload is removed, its entries are automatically garbage collected.
- `timestamp`: UTC timestamp of the log event.
- `severity`: Standardized log level (`DEBUG`, `INFO`, `WARN`, `ERROR`, `CRITICAL`).
- `service`: Microservice name (e.g. `auth-service`, `billing-service`, `api-gateway`).
- `request_id`: Correlation / trace ID (`Nullable`). Allows end-to-end distributed tracing.
- `message`: Free-form log message or stack trace.

### Indexing Strategy & Trade-offs
Four explicit indexes were created on `log_entries`:
1. `idx_log_entries_timestamp` on `timestamp`:
   - **Why:** Log analysis is almost exclusively time-bounded. Queries filter by `from` and `to`, and order results by latest-first. An index converts $O(N)$ full table scans into $O(\log N)$ B-Tree range scans.
2. `idx_log_entries_severity` on `severity`:
   - **Why:** Developers frequently filter for `ERROR` and `CRITICAL` entries during incidents.
3. `idx_log_entries_request_id` on `request_id`:
   - **Why:** Distributed trace correlation requires looking up all log entries matching a specific request ID across services instantly.
4. `idx_log_entries_ts_severity` on `(timestamp, severity)`:
   - **Why:** Composite index supporting high-frequency incident queries (e.g. "show errors from the last 24 hours").
5. `idx_log_entries_upload_id` on `upload_id`:
   - **Why:** Fast joins and cascade deletions.

**Trade-off Analysis:**
- *Read vs Write Cost:* Indexes accelerate reads drastically but add minimal overhead during bulk inserts ($O(\log N)$ tree balancing per index per inserted row). For a 7-day MVP and typical log volumes, read speed on search and dashboard loading far outweighs the write cost.

---

## 3. Search & Filter API Contract

### Endpoint
`GET /api/logs`

### Query Parameters

| Parameter | Type | Required | Default | Validation & Bounds | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `severity` | `string` | No | `None` | Case-insensitive; must be `DEBUG`, `INFO`, `WARN`, `ERROR`, or `CRITICAL` | Filter logs by severity level |
| `request_id` | `string` | No | `None` | Exact string match (no wildcards) | Trace logs for a specific request ID |
| `from` | `datetime` | No | `None` | Valid ISO-8601 string | Filter logs on or after this timestamp |
| `to` | `datetime` | No | `None` | Valid ISO-8601 string; must be `>= from` | Filter logs on or before this timestamp |
| `page` | `integer` | No | `1` | `ge=1` | 1-indexed page number |
| `limit` | `integer` | No | `50` | `ge=1, le=100` | Number of items per page |

### Success Response (HTTP 200 OK)
```json
{
  "total": 120,
  "page": 1,
  "limit": 50,
  "entries": [
    {
      "id": 104,
      "timestamp": "2026-10-20T12:00:00Z",
      "severity": "ERROR",
      "service": "auth-service",
      "request_id": "req-8f3k2",
      "message": "User authentication failed"
    }
  ]
}
```

### Error Responses
- **HTTP 400 Bad Request**:
  - Invalid severity value:
    ```json
    {"detail": "Invalid severity 'TRACE'. Allowed values are: CRITICAL, DEBUG, ERROR, INFO, WARN."}
    ```
  - Inverted date range (`from > to`):
    ```json
    {"detail": "The 'from' parameter must be earlier than or equal to the 'to' parameter."}
    ```
- **HTTP 422 Unprocessable Entity**:
  - Malformed ISO date format: `?from=not-a-date`
  - Pagination boundary violation: `?page=0` or `?limit=500`

---

## 4. Key Implementation Mechanisms

### A. Case-Insensitive Severity
Incoming severity strings are trimmed and upper-cased. The query uses `func.upper(LogEntry.severity) == normalized_severity` to guarantee case-insensitive matches regardless of the raw format stored in the database.

### B. Exact Request ID Matching
The query uses `LogEntry.request_id == clean_request_id` (SQL equality operator `=`), completely avoiding `LIKE` or `%` substrings. Substrings such as `req-alpha` will never falsely match `req-alpha-child`.

### C. Total Count Calculation
Total count is computed using `select(func.count(LogEntry.id)).where(*filters)` **before** applying `offset` and `limit`. This ensures the UI pagination bar accurately reports the full dataset size.

### D. Predictable Ordering
Queries enforce `.order_by(LogEntry.timestamp.desc(), LogEntry.id.desc())`.
The `id.desc()` serves as a deterministic tie-breaker if two log events share the exact same microsecond timestamp.

### E. Database Session Lifecycle
FastAPI's dependency injection (`Depends(get_db)`) yields a SQLAlchemy session inside a `try...finally` block, guaranteeing the session is closed and connections returned to the pool after every HTTP response.

---

## 5. Cross-Role Coordination Interfaces

### For Role 1 (Ingestion & Parsing Lead)
Role 1 can import the models and helpers directly from `app.models` and `app.crud`:
```python
from app.database import SessionLocal
from app.crud import create_upload, bulk_create_log_entries

db = SessionLocal()
upload = create_upload(db, filename="app.log", total_lines=len(raw_lines))
bulk_create_log_entries(db, upload_id=upload.id, entries_data=parsed_list)
db.close()
```

### For Role 3 (Analytics Lead)
Role 3 can run fast group-by aggregations on `LogEntry`:
```python
from sqlalchemy import select, func
from app.models import LogEntry

# Error breakdown by service
stmt = (
    select(LogEntry.service, func.count(LogEntry.id))
    .where(LogEntry.severity == "ERROR")
    .group_by(LogEntry.service)
)
```

### For Role 4 (Dashboard Lead)
Role 4 can consume `GET /api/logs` directly using `fetch()`:
```javascript
const res = await fetch(`/api/logs?severity=ERROR&page=1&limit=50`);
const { total, page, limit, entries } = await res.json();
```
An interactive explorer is already implemented in `static/index.html` and served at `/explorer`.

### For Role 5 (QA & Deployment Lead)
- Run tests: `pytest -v` (28 passing tests).
- Start server: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Seed data: `python3 seed_demo_data.py`.
