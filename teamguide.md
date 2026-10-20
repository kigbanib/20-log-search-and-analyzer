# Log Search & Analyzer — Team Guide (5 people, 7 days)

## 1. What we are building (plain English)

A **mini Splunk/Datadog Logs**. Real applications constantly write log lines
(timestamp, severity, service, request ID, message). When something breaks,
engineers dig through thousands of lines to find the cause. Our app does that
digging:

> **Upload a log file → it gets parsed and stored → filter by severity →
> search by request ID → see which errors recur most often.**

That single flow, done well and tested, is the entire MVP.

### Out of scope (do NOT build these in the week)

- User accounts / auth / login
- Real-time log streaming from live servers
- Graphs/charts beyond a simple table or list (nice-to-have only)
- Multi-file comparison, alerting, retention policies

The rubric explicitly says: _"A smaller, complete, tested MVP should score
higher than a broad but broken implementation."_

---

## 2. The five roles

### Role 1 — Ingestion & Parser Lead

**Owns:** everything between "user picks a file" and "clean rows ready to store."

- Write the log format spec (see §4) and get team sign-off on Day 1.
- Build `POST /api/logs/upload` (multipart file).
- Line-by-line parser: validate each line, collect malformed ones with line
  numbers, never crash the whole upload on one bad line.
- Enforce file size limit (e.g. 5 MB) and file type check.
- Unit tests for the parser (valid line, missing field, unknown severity,
  garbage line).
- **One technical decision to explain at demo:** e.g. "we skip-and-report bad
  lines instead of rejecting the file, because real logs are always partly
  corrupt."

### Role 2 — Search & Filter API Lead

**Owns:** database schema and query endpoints.

- Define SQLAlchemy models + indexes (see §5).
- Build `GET /api/logs` with query params: `severity`, `request_id`,
  `from`, `to`, `page`, `limit`.
- Severity filter must be case-insensitive; request-ID search should be exact
  match (partial match is a stretch goal only).
- Pagination: never return 100k rows at once (default limit 50).
- **One technical decision:** e.g. "we indexed severity and request_id because
  those are the demo's hot query paths."

### Role 3 — Analytics & Reporting Lead

**Owns:** recurring errors + monitoring.

- Build `GET /api/stats/errors`: group ERROR/CRITICAL entries by normalized
  message, return count, first_seen, last_seen, a few sample request_ids.
- Build `GET /api/stats/summary`: totals per severity, per service (feeds a
  small dashboard panel).
- Build `GET /api/health`: app + DB status, last upload time, total entries
  (this satisfies the "basic monitoring/reporting" core feature).
- **One technical decision:** e.g. "we normalize error messages by stripping
  numbers/IDs so 'timeout after 5023ms' and 'timeout after 3102ms' group
  together."

### Role 4 — Dashboard (Frontend) Lead

**Owns:** every screen and state the user sees.

- Upload form (with progress/success/failure feedback, showing skipped-line
  report from Role 1's response).
- Log table: severity dropdown, request-ID search box, date range, pagination
  controls.
- "Top recurring errors" panel (click an error → filters the table).
- **All four states for every panel:** loading, empty, error, data. Judges
  notice empty states.
- Keep it explainable in 60 seconds during the demo.

### Role 5 — Test Data, QA & DevOps Lead

**Owns:** synthetic data, test suite, deployment, docs, demo script.

- **Day 1 deliverable:** `scripts/generate_logs.py` producing realistic
  JSONL (see §4) — multiple days of timestamps, 4–6 services, recurring error
  messages (so the stats panel has something to show), some lines with no
  request_id.
- Edge-case datasets: empty file, file with 30% malformed lines, file with
  unknown severities, oversized file, a non-log file renamed to `.log`.
- Integration tests for the API (happy path + the major failure path).
- Deployment to Render; seed-on-startup so the live demo always has data.
- README (see §10) and the demo script (see §9). Facilitates code reviews.

> ⚠️ Roles 1–3 are all backend. Pair them deliberately: Role 1 needs Role 2's
> model to store rows → agree on the model in the first hour of Day 1. Role 4
> works against mock JSON matching the contract until endpoints are live.

---

## 3. Recommended stack (and why)

| Layer    | Choice                          | Why                                                                             | Alternative                                                  |
| -------- | ------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Backend  | Python + FastAPI                | Auto-generated Swagger docs at /docs = free demo asset; very little boilerplate | Node/Express, Flask                                          |
| DB       | SQLite + SQLAlchemy             | Zero setup, file-based, perfect for MVP scale                                   | Postgres on Neon/Supabase if someone is comfortable          |
| Frontend | Plain HTML/JS served by FastAPI | ONE deploy, no CORS, no second URL                                              | React+Vite on Vercel (nicer UI, costs you CORS + 2nd deploy) |
| Deploy   | Render free tier                | Runs FastAPI + serves static + SQLite file                                      | Railway, Fly.io                                              |

**Trade-off to be able to state at demo:** SQLite + free Render tier means no
horizontal scaling and the free instance sleeps (cold start ~30s). Acceptable
for an MVP; Postgres + a paid tier is the "next improvement."

Environment variables (README must list them): `DATABASE_URL`,
`MAX_UPLOAD_MB`, `CORS_ORIGIN`, `PORT`.

---

## 4. Log format (lock this on Day 1)

**Primary: JSON Lines (.jsonl / .log), one object per line:**

```json
{
  "timestamp": "2026-10-20T10:15:04Z",
  "severity": "ERROR",
  "service": "auth-service",
  "request_id": "req-8f3k2",
  "message": "Database connection timeout"
}
```

Validation rules (Role 1 enforces):

- `timestamp`: ISO-8601, required → else line is malformed
- `severity`: one of DEBUG, INFO, WARN, ERROR, CRITICAL (uppercase; parser
  uppercases input) → unknown value = malformed line
- `service`: non-empty string, required
- `request_id`: optional; missing → stored as null (and simply won't match
  request-ID searches)
- `message`: non-empty string, required

(Optional spice, only after MVP works: also accept the classic text format
`2026-10-20 10:15:04 ERROR [auth-service] req-8f3k2 Database connection timeout`
— it shows off parsing skill. Do NOT start with both.)

---

## 5. Data model

**Table: uploads** (one row per uploaded file — the "batch")
| column | type | notes |
|--------|------|-------|
| id | int PK | |
| filename | text | |
| uploaded_at | datetime | |
| total_lines / parsed_lines / failed_lines | int | report to user |
| status | text | `ok`, `partial` (some lines failed), `failed` |

**Table: log_entries**
| column | type | notes |
|--------|------|-------|
| id | int PK | |
| upload_id | FK → uploads | so a bad upload can be traced/deleted |
| timestamp | datetime | **indexed** |
| severity | text (enum) | **indexed** |
| service | text | |
| request_id | text, nullable | **indexed** |
| message | text | |

Two tables (not one) earns "data correctness/modeling" points: an upload is a
real entity the user cares about ("what happened to my file?").

---

## 6. API contract (lock on Day 1 — everyone codes against this)

**`POST /api/logs/upload`** — multipart form, field name `file`
→ 200 (even with skipped lines) or 400 (empty/unreadable/oversized):

```json
{
  "upload_id": 7,
  "status": "partial",
  "total_lines": 500,
  "parsed_lines": 487,
  "failed_lines": 13,
  "errors": [{ "line": 12, "reason": "unknown severity 'FATAL'" }]
}
```

**`GET /api/logs?severity=ERROR&request_id=req-8f3k2&from=...&to=...&page=1&limit=50`**

```json
{
  "total": 134,
  "page": 1,
  "limit": 50,
  "entries": [
    {
      "id": 12,
      "timestamp": "...",
      "severity": "ERROR",
      "service": "auth-service",
      "request_id": "req-8f3k2",
      "message": "Database connection timeout"
    }
  ]
}
```

**`GET /api/stats/errors?top=10`**

```json
{
  "errors": [
    {
      "message": "Database connection timeout",
      "severity": "ERROR",
      "count": 47,
      "first_seen": "...",
      "last_seen": "...",
      "sample_request_ids": ["req-8f3k2", "req-9aa11"]
    }
  ]
}
```

**`GET /api/health`** → `{"status": "ok", "db": "ok", "total_entries": 12403, "last_upload": "..."}`

---

## 7. Day-by-day plan

- **Day 1 — Align (whole team, ~2h meeting + solo setup):** agree MVP scope,
  log format, data model, API contract (paste §4–6 into your repo as
  `docs/`); set up repo (protected `main`, branch naming `feature/parser`,
  PR template, at least 1 reviewer per PR); skeleton apps that run.
  Role 5 ships the log generator **today**. Role 4 starts UI with mock JSON.
- **Days 2–3 — Parallel build:** each role builds per §2. Mock anything not
  ready. **Exit criteria Day 3: walking skeleton — upload a file from the UI
  and see its rows in the table, however rough.**
- **Day 4 — Integration + feature freeze:** swap all mocks for real calls,
  merge PRs, fix contract mismatches. No new features after today.
- **Day 5 — Harden:** run Role 5's edge-case datasets; write the failure-path
  test; security pass (size limit, file type, ORM parameterized queries,
  no eval/exec on uploaded content); fix bugs.
- **Day 6 — Deploy + docs:** live URL, seed-on-startup, README complete
  (§10), screenshots, demo script rehearsed.
- **Day 7 — Present + retro:** run §9; each person states their component +
  one technical decision; 15-min team retrospective (what went well, what
  we'd do differently) — have it ready to mention if asked.

---

## 8. Test strategy (rubric = 15 pts — be specific)

**Parser unit tests (Role 1):** valid line parses; missing timestamp →
malformed; lowercase `error` → normalized to ERROR; unknown severity →
malformed with line number; missing request_id → null, still stored.

**API tests (Role 2 + 5):**

- Happy path: upload `sample_valid.log` (5-edge dataset) → filter by
  severity=ERROR returns only errors → search existing request_id returns its
  lines → stats groups the recurring error.
- **Major failure path (required by the brief):** upload file with 30%
  garbage lines → HTTP 200, status `partial`, failed_lines counted, bad line
  numbers reported — and nothing crashes.
- No-match request_id → 200 with empty list (UI shows empty state, not error).
- Oversized file → clean 400 with message.

Evidence for judges: screenshot of passing tests in CI or terminal, and the
edge-case datasets committed in `testdata/`.

---

## 9. Demo script (~7 minutes)

1. **Problem (30s):** "Production broke — 10,000 log lines. Which error
   matters, and what did request req-8f3k2 actually do?"
2. **Upload (1 min):** upload seeded file live → show parsed/skipped report.
3. **Filter (1 min):** dropdown to ERROR — only errors, fast.
4. **Request trace (1 min):** search `req-8f3k2` — the story of one request
   across services, in time order.
5. **Recurring errors (1 min):** stats panel — top error ×47, first/last
   seen; click it → table filters.
6. **Architecture (1 min):** one slide/diagram: UI → FastAPI → SQLite; state
   the two trade-offs honestly (SQLite scale, free-tier cold start).
7. **Contributions (1.5 min):** 20s each — component + one decision.
8. Close with "what's next": auth, real file streaming, Postgres.

**Honesty rule from the brief:** never present a mock as working. If something
is unfinished, say so and put it under "next improvements" — judges reward it.

---

## 10. README checklist (rubric = 10 pts)

- One-paragraph description + screenshot(s)
- Setup: prerequisites, `pip install -r requirements.txt`, env vars
  (`DATABASE_URL`, `MAX_UPLOAD_MB`, `CORS_ORIGIN`, `PORT`), run command
- Live demo URL + how to regenerate seed data (`python scripts/generate_logs.py`)
- Log format spec + API contract summary
- Architecture diagram (boxes and arrows is fine) + key decisions
- Known limitations (honest list) + next improvements
- Team roster with each person's role/component
- **Disclosure of borrowed code, libraries, templates, and any AI/code-gen
  tools used** — required by the judging safeguards

---

## 11. Rubric cheat-sheet (100 pts)

| Criterion                      | Pts | How we win it                                                                                            |
| ------------------------------ | --- | -------------------------------------------------------------------------------------------------------- |
| Core functionality             | 25  | Walking skeleton early; one flawless end-to-end demo flow                                                |
| Engineering & data correctness | 20  | Two-table model, real indexes, validation on every input, clean module boundaries (parser / api / stats) |
| Testing & reliability          | 15  | §8 test suite + committed edge-case datasets                                                             |
| Collaboration & Git            | 15  | Branch per feature, small PRs, every PR reviewed by someone else, meaningful commit messages             |
| Usability & demo               | 10  | Seeded live URL; loading/empty/error states; 60-second learnability                                      |
| Docs & setup                   | 10  | README per §10, run-from-scratch works                                                                   |
| Scope & delivery               | 5   | Ruthlessly cut optionals; ship on time                                                                   |

## 12. Pitfalls to avoid

- Arguing about the log format past Day 1 — lock it and move.
- Failing an entire upload because 3 lines are bad (skip-and-report instead).
- Returning unbounded query results (always paginate).
- Building auth/charts/extras before the core flow works end-to-end.
- One person deploying on Day 7 for the first time — deploy a "hello world"
  version on Day 2 or 3 to derisk.
- Pushing to main directly (the brief forbids it) or committing credentials.
