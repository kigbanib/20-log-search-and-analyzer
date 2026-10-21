# Log Search & Analyzer — Mini Splunk / Datadog Logs

> **One-liner:** Upload a JSONL log file → it gets parsed and stored → filter by severity → search by request ID → see which errors recur most often. One flow, done well and tested — the entire MVP.

![Python](https://img.shields.io/badge/Python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green) ![SQLite](https://img.shields.io/badge/SQLite-SQLAlchemy_2.0-lightgrey) ![Tests](https://img.shields.io/badge/tests-48_passed-brightgreen)
[![Deploy to Render](https://binaries.render.com/docs/render-button.svg)](https://render.com/deploy?repo=kigbanib/20-log-search-and-analyzer)

**Live demo (local):** `http://localhost:8000` → dashboard at `/` + Swagger at `/docs` + explorer at `/explorer`  
**Live demo (Render):** _pending — paste the `https://<service>.onrender.com` URL here after the first deploy ([how to deploy →](docs/render-deploy.md))_  
**Repo:** `kigbanib/20-log-search-and-analyzer` — integrated on `arena/d8852790…` (ready to PR to `develop`)

---

## 📸 Screenshot
```
┌──────────────┐     POST /api/logs/upload      ┌──────────────┐     GET /api/logs?severity=…     ┌──────────┐
│  Dashboard   │ ─────────────────────────────► │   FastAPI    │ ───────────────────────────────► │ SQLite   │
│  (frontend/) │  JSONL → ParsedLog/ParseError   │  app/main.py │  SQLAlchemy + indexes           │ logs.db  │
│  upload +    │ ◄─────────────────────────────  │  routers/*   │ ◄────────────────────────────── │ uploads  │
│  table +     │  {upload_id,status,errors[]}    │  services/*  │  {total,page,limit,entries}     │ log_entries│
│  stats       │           GET /api/stats/*      └──────────────┘  GET /api/health                └──────────┘
└──────────────┘ ─────────────────────────────► ─────────────────────────────► ────────────────────────────────┘
```
*UI: upload card → severity dropdown + request-ID search + date range + pagination → “Top recurring errors” chips click-to-filter.*

---

## 🧩 Core Features (MVP — teamguide §6)
- **Upload:** `POST /api/logs/upload` (multipart `file` .log/.jsonl/.txt, 5 MB limit) — skip-and-report, never crashes on bad lines
- **Search:** `GET /api/logs?severity=&request_id=&from=&to=&page=&limit=` — case-insensitive severity, exact request-ID, date range, pagination (default 50, max 100)
- **Analytics:** `GET /api/stats/errors?top=` (normalized message grouping) + `GET /api/stats/summary` (by severity/service) + `GET /api/health` (db + last upload)
- **Dashboard:** 4 states per panel (loading/empty/error/data), health badge, upload report with skipped-line details

---

## 🏗 Architecture

**Stack:** Python 3.11 + FastAPI (auto Swagger at `/docs`) + SQLite + SQLAlchemy 2.0 + plain HTML/JS served by FastAPI — **ONE deploy on Render**, no CORS split.

**Data model (2 tables, per teamguide §5):**
- `uploads(id, filename, uploaded_at, total_lines, parsed_lines, failed_lines, status)` — one row per file batch
- `log_entries(id, upload_id FK CASCADE, timestamp indexed, severity indexed, request_id indexed nullable, message, service)` + composite index `(timestamp, severity)`

**Key decisions (for demo):**
1. *Skip-and-report not reject-file* — real logs are partly corrupt; blank lines ignored
2. *Indexed severity/request_id/timestamp* — hot demo paths are `ERROR` filter + `req-8f3k2` trace
3. *SQLite over Postgres for MVP* — zero setup, fine for <100k rows; Postgres is “next improvement”
4. *Normalize errors by stripping numbers/IDs* — `timeout after 5023ms` and `3102ms` group as one recurring error

```
frontend/            → Role 4 Dashboard (Golden)
  index.html, css/styles.css, js/api.js (USE_MOCK=false), js/app.js, js/mock.js
app/
  parser/            → Role 1 Ingestion (mabegund) — schema.py + parser.py
  services/ingestion.py → Role 1 — DB-backed process_upload()
  routers/
    upload.py        → Role 1 — POST /api/logs/upload
    logs.py          → Role 2 Search (ecstasy1) — GET /api/logs
    analytics.py     → Role 3 Analytics (kigbanib) — /api/stats/* + /api/health
  models.py, database.py, config.py, schemas.py, crud.py → Role 2
scripts/generate_logs.py + testdata/* → Role 5 QA/DevOps
app/seed.py (+ root seed_demo_data.py CLI alias) → Role 5 — idempotent demo seed, runs at startup on Render
render.yaml + .python-version + .env.example → Role 5 — Render Blueprint (one free web service)
```

---

## 🚀 Setup & Run

### Prerequisites
- Python 3.11+, `pip`, Node 18+ (for frontend mock tests only)

### 1. Install
```bash
git clone https://github.com/kigbanib/20-log-search-and-analyzer.git
cd 20-log-search-and-analyzer
git checkout arena/d8852790-20-log-search-and-analyzer   # or develop after PR merge
pip install -r requirements.txt
```

### 2. Env vars
```bash
cp .env.example .env   # edit if needed
# DATABASE_URL=sqlite:///./logs.db
# MAX_UPLOAD_MB=5
# CORS_ORIGIN=*
# PORT=8000
# SEED_ON_START=true   # seed demo rows at startup when the DB is empty (auto-on under Render)
```

### 3. Generate data & seed
```bash
python scripts/generate_logs.py            # -> testdata/sample_valid.jsonl (500 lines)
python scripts/generate_logs.py --all      # -> testdata/empty.log, malformed_30pct.*, unknown_severities.log, fake_image.log, sample_5.log
python seed_demo_data.py                   # seeds logs.db with 17 demo entries (alias of `python -m app.seed`)
python -m app.seed --force                 # add another demo batch even if rows exist
```

### 4. Run
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# → http://localhost:8000        (dashboard)
# → http://localhost:8000/docs   (Swagger)
# → http://localhost:8000/api/health
```

### 5. Test
```bash
pytest -v                     # 48 backend tests (parser 12 + logs 13 + models 7 + integration 4 + upload 5 + analytics 3)
node frontend/tests/api.test.js  # 15 frontend mock tests (happy + failure paths)
```

---

## 📖 Log Format (locked Day 1 — `docs/log-format.md`)
JSON Lines, one object per line, blank lines ignored:
```json
{
  "timestamp": "2026-10-20T10:15:04Z",
  "severity": "ERROR",
  "service": "auth-service",
  "request_id": "req-8f3k2",
  "message": "Database connection timeout"
}
```
- `timestamp` ISO-8601 required → else malformed
- `severity` one of `DEBUG,INFO,WARN,ERROR,CRITICAL` (uppercased) → unknown = malformed
- `service` non-empty required
- `request_id` optional → stored as `null` if missing
- `message` non-empty required

---

## 🔌 API Contract (locked Day 1 — `docs/api-contract.md`)

**POST /api/logs/upload** — multipart `file`
```json
{
  "upload_id": 7,
  "filename": "app.log",
  "status": "partial",          // ok | partial | failed
  "total_lines": 500,
  "parsed_lines": 487,
  "failed_lines": 13,
  "errors": [{"line":12,"reason":"unknown severity 'FATAL'"}] // capped 50
}
```
`400` on empty / oversized (>5 MB) / wrong extension.

**GET /api/logs?severity=ERROR&request_id=req-8f3k2&from=2026-10-20T00:00:00Z&to=2026-10-21T00:00:00Z&page=1&limit=50**
```json
{"total":134,"page":1,"limit":50,"entries":[{"id":12,"timestamp":"…","severity":"ERROR","service":"auth-service","request_id":"req-8f3k2","message":"…"}]}
```

**GET /api/stats/errors?top=10** → grouped by normalized `message` (numbers → `<value>`, IDs → `<id>`)
```json
{"errors":[{"message":"Database connection timeout","severity":"ERROR","count":47,"first_seen":"…","last_seen":"…","sample_request_ids":["req-8f3k2"] }]}
```

**GET /api/stats/summary** → `{"total_entries":12403,"by_severity":{…},"by_service":{…}}`

**GET /api/health** → `{"status":"ok","db":"ok","total_entries":571,"last_upload":"…","service":"Log Search & Analyzer","version":"1.0.0"}`

---

## 🧪 Test Strategy (rubric 15pts — `tests/`)

**Parser (Role 1):** valid line, missing timestamp → malformed, lowercase `error` → `ERROR`, unknown severity with line number, missing/null `request_id` → `null`, garbage → ParseError, batch `2+2`, empty file, **30% garbage (70/30)** major failure path, allowed set.

**API (Role 2+5):** happy path upload → filter `severity=ERROR` → trace `req-8f3k2` → stats groups recurring error; **major failure path** 30% garbage → `200 partial` with line numbers; no-match `request_id` → `200 []`; oversized → `400`; invalid extension → `400`; pagination no overlap.

**Analytics (Role 3):** normalization (`5023ms`/`3102ms` same group), summary totals, health.

---

## 🎬 Demo Script (7 min — teamguide §9)
1. Problem (30s): “Production broke — 10k log lines. Which error matters, what did `req-8f3k2` do?”
2. Upload (1m): upload `sample_valid.jsonl` live → show `487/500 partial` report
3. Filter (1m): dropdown to `ERROR` — only errors, fast (indexed)
4. Trace (1m): search `req-8f3k2` — story across services, time-ordered
5. Recurring (1m): stats panel — top error ×47, click chip → table filters
6. Arch (1m): UI → FastAPI → SQLite diagram; trade-offs (SQLite scale, free-tier cold start)
7. Contributions (1.5m): each role 20s + one technical decision

---

## 👥 Team Roster (5 roles)

| Person | Branch | Component |
|--------|--------|-----------|
| mabegund | `Ingestion` | Ingestion & Parser Lead — `docs/log-format.md`, `app/parser/*`, `POST /api/logs/upload`, `tests/test_parser.py` |
| ecstasy1 | `search` | Search & Filter API Lead — `app/models.py`, `database.py`, `crud.py`, `GET /api/logs`, indexes, `seed_demo_data.py` |
| kigbanib | `analytics` | Analytics & Reporting Lead — `role3_analytics.py` → `app/routers/analytics.py` (`/stats/*` + health) |
| Golden (snrboi557) | `frontend` | Dashboard Lead — `frontend/` (upload + table + stats, 4 states) |
| Role 5 (DevOps/QA) — **gap filled** | — | `scripts/generate_logs.py`, `testdata/` edge-case sets, `tests/test_upload|analytics.py`, `.env.example`, deploy docs |

See `MERGE_REPORT.md` for merge details + missing-file attribution.

---

## ⚠️ Known Limitations & Next Improvements
- SQLite + free Render tier → no horizontal scaling, ~1 min cold start after 15 min idle, and an **ephemeral filesystem** (SQLite file + uploads are wiped on every redeploy/restart/spin-down; `SEED_ON_START` re-seeds so the demo never opens empty) → **Next:** Postgres on Render Free/Neon + paid tier for a persistent disk
- No auth/auditing — **Next:** API key + upload audit log
- No real-time tail — **Next:** polling/WebSocket for live logs
- Frontend no build step — **Next:** Vite + proper bundling
- `MAX_UPLOAD_MB` enforced in-process — **Next:** nginx limit + S3

---

## 📦 Deployment

**Full walkthrough: [`docs/render-deploy.md`](docs/render-deploy.md)** — decision table, every dashboard click, verification checklist, and a troubleshooting list of the real failure modes. Summary:

| Setting | Value |
|---|---|
| Service type | **Web Service** (Python runtime) — API + dashboard in ONE deploy |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/health` |
| Python version | `3.11` (pinned in `.python-version`; Render's default is now 3.14) |
| Plan | Free (spins down after 15 min idle, ~1 min cold start) |
| Config | `render.yaml` Blueprint — **New + → Blueprint** pre-fills everything |

**Data on Render:** the filesystem is *ephemeral*, so a SQLite `logs.db` is wiped on
every redeploy/restart/spin-down. `init_db()` + `SEED_ON_START=true` re-create the
schema and re-seed the 17 demo entries at startup, so the dashboard is never empty —
but for uploaded files to survive, point `DATABASE_URL` at a Postgres instance (Render
Free, expires in 30 days, or Neon/Supabase free). The app rewrites `postgres://` →
`postgresql://` and `psycopg2-binary` is already in `requirements.txt`, so the switch is
one env var and a restart. No one-off jobs / SSH on the free tier, which is why seeding
happens in the app lifespan instead of a deploy hook.

**Vercel alt:** `frontend/` as a static site + `/api` proxied to Render — costs you a
second deploy and real CORS config (`CORS_ORIGIN=https://your-app.vercel.app`). Not
recommended for the demo.

---

## 📚 Disclosure

- **Libraries:** FastAPI, SQLAlchemy, Pydantic, Uvicorn, pytest, httpx, python-multipart (see `requirements.txt`)
- **Borrowed:** `static/index.html` explorer from Role 2 draft, adapted
- **AI/code-gen:** used for boilerplate docs/tests, all logic reviewed
- **Env vars:** `DATABASE_URL`, `MAX_UPLOAD_MB`, `CORS_ORIGIN`, `PORT`, `SEED_ON_START`

---

## 📝 License
MIT — MVP for Developer Tools & Automation course.
