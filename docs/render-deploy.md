# Deploying Log Search & Analyzer on Render — step by step

Audience: whoever on the team is doing the deploy (Role 5 per `teamguide.md`), on a
machine with Git + a browser. Expected time: **~15 minutes** (SQLite) or **~25
minutes** (Postgres). Do it at least twice before demo day — once for the live URL,
once as a timed dry run.

Everything below is verified against this repo and Render's current docs. Two things
in this project are unusual and they are the source of almost every failed deploy:

1. **One service serves both API and UI.** FastAPI serves `frontend/` itself, so
   there is exactly one URL and no CORS dance. If the UI looks unstyled, the static
   mounts are broken — not the CSS.
2. **Render's filesystem is ephemeral.** A SQLite `logs.db` is deleted on every
   redeploy, restart, and free-tier spin-down. This is a *platform* behaviour, not a
   bug: it is the first thing to decide (Step 1).

---

## 0. TL;DR

```bash
# repo already carries render.yaml + .python-version (see Step 2)
git push origin main                     # Render auto-deploys on push
```

Dashboard: **New + → Blueprint → pick this repo → Free → Frankfurt → deploy.**
Settings Render reads from `render.yaml`:

| Setting | Value |
|---|---|
| Runtime | Python (version pinned by `.python-version` → 3.11) |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/health` |
| Env vars | `SEED_ON_START=true`, `MAX_UPLOAD_MB=5`, `CORS_ORIGIN=*`, `DATABASE_URL` (optional) |

Then verify:

```bash
curl -s https://<your-service>.onrender.com/api/health
# {"status":"ok","db":"ok","total_entries":17,...}
```

Steps 1–9 explain each choice, and Step 11 is the list of errors you will actually hit.

---

## 1. Decide where the data lives (do this first, it changes the config)

| | **A. SQLite (default)** | **B. Postgres (recommended)** |
|---|---|---|
| Setup | none | 5 min, one extra button |
| Cost | $0 | $0 (Render Free) or $0 (Neon/Supabase free) |
| Survives redeploy? | ❌ no — wiped every deploy | ✅ yes |
| Survives 15-min idle spin-down? | ❌ no | ✅ yes |
| Uploaded demo files still there when you click around? | only while the service stays awake | always |
| Caveats | single writer; demo data is re-seeded on each boot | Render **Free** Postgres expires 30 days after creation (14-day grace, then deleted); 1 free DB per workspace; 1 GB |

**Recommendation for the demo: B (Postgres).** The demo script uploads a file, then
filters it, traces `req-8f3k2`, and shows recurring errors. With SQLite, if the
service spins down between those steps (or you redeploy to fix a typo right before
presenting) the upload is gone and step 3 onwards shows an empty table. With
Postgres the data survives everything except the 30-day free expiry.

If you would rather keep the zero-setup story for the presentation, choose A and
mentally accept: *the seeded demo dataset is always there (it re-seeds on boot),
but anything you upload live lasts only for that session.* That is a legitimately
good trade-off to state out loud at the demo — see Step 12.

`psycopg2-binary` is already in `requirements.txt`, so switching later is one env var
and a restart — no code change. That is why you can start with A and move to B.

---

## 2. Prepare the repo (already done — verify, don't re-do)

These files are what make the deploy work. Confirm they are committed on the branch
you intend to deploy:

| File | Why it exists |
|---|---|
| `render.yaml` | Blueprint: one free Python web service, correct commands, health path |
| `.python-version` (`3.11`) | **Required.** Render's default Python for services created since 2026-10-12 is **3.14.8**; your README, badges and CI say 3.11. Pinning keeps "works on my machine" true on Render |
| `requirements.txt` | has `python-multipart` (upload endpoint 500s without it) and `psycopg2-binary` (Postgres) |
| `app/config.py` | anchors relative SQLite paths + static dirs to the repo root, reads `SEED_ON_START` |
| `app/database.py` | `pool_pre_ping`/`pool_recycle` on Postgres, because a free Render DB can be restarted for maintenance at any time |
| `app/main.py` | mounts `/css` + `/js` by absolute path and seeds on startup |
| `app/seed.py` | the 17-entry demo dataset, importable by both the CLI and startup |

Checks before you touch Render:

```bash
git status --short                 # clean, nothing important uncommitted
pytest -q                          # 48 passed — deploy green only
python -m app.seed                 # "Successfully seeded 17 demo log entries!"
python -m app.seed                 # run twice: must say "nothing seeded" (idempotent)
uvicorn app.main:app --port 8000   # open http://localhost:8000 and see a styled dashboard
```

If the dashboard renders grey and unstyled locally, stop — fix that first; Render
will inherit the problem.

**Branch:** Render deploys one branch (`branch:` in `render.yaml`, currently `main`).
If your team is still reviewing on `develop` or a feature branch, either merge to
`main` (recommended) or change `branch:` in `render.yaml` to that branch. Render
redeploys automatically on every push to that branch — which is convenient, and also
means "push a fix 5 minutes before the demo" wipes SQLite data (Step 1).

---

## 3. Create the Render account + connect GitHub

1. Go to <https://dashboard.render.com/register> and sign up **with your GitHub
   account** (much easier than a separate email account + manual repo access).
   No credit card is needed for the Free plan.
2. On the "Connect a Git provider" screen, click **Add Account → GitHub App (recommended)**
   and install the Render app.
3. **This is the step teams get stuck on:** if the repo does not appear in the list,
   Render's GitHub App is not authorized for it. On GitHub:
   *Settings → Applications → Render → Repository access → Only select repositories*
   → tick `kigbanib/20-log-search-and-analyzer`. Then refresh Render's dashboard.
4. Whoever's account owns the repo should do the deploy, or add the rest of the team
   as **workspace members** (Dashboard → your workspace → Members → Invite) so more
   than one person isn't blocked on one login at demo time. Teammates need Render
   accounts; the free plan allows up to 25 services per workspace.

Optional but useful: install the CLI now, so you can validate the Blueprint before
pushing (needs v2.7.0+ for this command):

```bash
brew install render        # or: winget install render.cli
render blueprints validate render.yaml     # run in the repo root
```

Expected output: nothing (exit 0). If it prints `services[0].branch ... could not be
found`, your `branch:` value doesn't exist on the remote — fix it before deploying.
If you skip this, VS Code's Red Hat YAML extension validates `render.yaml` against
the same schema, or you find out at Step 5.

---

## 4. (Recommended) Create the database first

Do this **before** creating the service so the DB is in the same region and Render
can wire the connection string automatically.

1. <https://dashboard.render.com/new/database> (or **New + → Postgres**).
2. **Name:** `logsearch-db`. **Database:** `logsearch`. **User:** leave the generated one.
3. **Region:** pick the same region you will pick for the web service. This matters
   twice: private networking only works within a region, and a service's region
   **cannot be changed after creation**. For Port Harcourt, **Frankfurt** is the
   closest Render region (~120 ms); `oregon` is Render's default and ~230 ms.
4. Compute plan: **Free** (1 GB, single free DB per workspace, **expires after 30
   days** — mark your calendar if the project lives on). If your team wants a
   database that outlives the course, use Neon or Supabase's free Postgres instead
   and paste its connection string as `DATABASE_URL`; the app works with either.
5. Click **Create Database**, then on the new DB's page copy the
   **`Internal connection string`** (the *Internal* one — External is for your laptop).

Add it to the **web service** as the `DATABASE_URL` environment variable in
plaintext (not a secret) so both build and runtime see it. If instead you let the
Blueprint create the DB, Render injects it via `fromDatabase` (`render.yaml` has a
commented `databases:` block for that) — but only *after* the service exists, so it
needs a "Manual Deploy" to pick the value up.

You do **not** need to run migrations or create tables by hand: `init_db()` in the
app's lifespan does `create_all` on boot, and free-tier services cannot run Render's
one-off jobs anyway.

---

## 5. Create the web service

### Path A — Blueprint (use this; `render.yaml` is in the repo)

1. **New + → Blueprint.** (Not "Web Service" — that flow ignores `render.yaml`.)
2. Select `kigbanib/20-log-search-and-analyzer`, branch `main`.
3. Render parses `render.yaml` and shows a plan with one web service (+ DB if you
   uncommented `databases:`). Confirm **Free** is selected as the compute plan.
4. It prompts for `DATABASE_URL` because `render.yaml` marks it `sync: false` —
   paste the string from Step 4, or **leave it empty** for the SQLite path.
5. **Apply Blueprint.** Build starts immediately.

### Path B — Manual (if the Blueprint flow confuses you the first time)

**New + → Web Service** → same repo/branch, then type these in exactly:

| Field | Value |
|---|---|
| Environment | `Python 3` (auto-detected) |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Region | `Frankfurt` (or `Oregon` if Free isn't offered — decide now, it's permanent) |
| Instance Type | `Free` |
| Health Check Path | `Advanced → Health Check Path → /api/health` |
| Environment variables | `SEED_ON_START=true`, `MAX_UPLOAD_MB=5`, `CORS_ORIGIN=*`, `DATABASE_URL=…` |

The `$PORT` part is not decoration. Render assigns the port at runtime (default
10000); hardcoding `--port 8000` builds fine, starts fine, and then fails the port
scan. `--host 0.0.0.0` is equally required — `127.0.0.1` is unreachable from outside
the container. Both symptoms look identical: **"No open ports detected"**.

---

## 6. Env vars: what each one does here

Read in `app/config.py`; set them in Render's **Environment** tab (or `render.yaml`).

| Key | Value on Render | If you get it wrong |
|---|---|---|
| `DATABASE_URL` | Postgres internal URL, or empty for SQLite | A wrong host / cross-region / SSL setting shows up as a 500 on `/api/health` and `connection timed out` in the runtime log |
| `SEED_ON_START` | `true` | `false` + empty DB = a blank dashboard during the demo. `true` only inserts when the DB is empty, so it never duplicates your uploaded data |
| `MAX_UPLOAD_MB` | `5` | Raise it and the UI's own 5 MB guard (`frontend/js/api.js`) still blocks first — change both |
| `CORS_ORIGIN` | `*` | Only relevant if you host `frontend/` separately (e.g. Vercel); then set it to that exact origin, no trailing slash |
| `PORT` | **don't set it** | Render injects it. Setting `PORT=8000` in the dashboard while the start command uses `$PORT` is a classic self-inflicted port mismatch |

Two details worth knowing:

- **Env var changes don't take effect until the next deploy.** When you edit one,
  pick **"Save and deploy"** (or Manual Deploy → Deploy latest commit) — "Save only"
  leaves the running process on the old value, which is how "I set it but nothing
  changed" happens. Also useful: Render injects `RENDER` (always true — this is what
  `SEED_ON_START` defaults on from) and `RENDER_EXTERNAL_URL` (your public
  `*.onrender.com` URL — paste that into `CORS_ORIGIN` if you ever split the
  frontend onto Vercel/Netlify).
- The app **does not** read `.env` at runtime — there is no `python-dotenv`
  dependency. `.env` is a local convention only; on Render the dashboard *is* your
  `.env`. Don't push a `.env` (it's gitignored) expecting it to be honoured.
- `python -m app.seed` and `uvicorn` are run from the repo root by Render
  (`/opt/render/project/src`), which is why relative paths work at all. Because
  `app/config.py` now resolves them against the repo root, the app also survives a
  `rootDir`/Dockerfile change — but keep the start command simple anyway.

---

## 7. First deploy: read the log

Service page → **Events** tab for deploy status, **Logs** for runtime output. A good
first deploy looks like:

```
==> Building…
==> Running build command 'pip install -r requirements.txt'…
Successfully installed fastapi-… uvicorn-… psycopg2-binary-… sqlalchemy-2.0.…
==> Uploading build…
==> Running 'uvicorn app.main:app --host 0.0.0.0 --port $PORT'
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Seeded 17 demo log entries (empty database).     ← only on an empty DB
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
==> Your service is live 🥳
```

That `Seeded 17 demo log entries` line is your proof that `SEED_ON_START` reached the
app — if it's missing on a fresh deploy, the env var isn't set and the dashboard will
be empty. (It deliberately logs through `uvicorn.error`, because plain `app.*`
loggers aren't configured by uvicorn and their INFO lines never reach Render's logs.)

Watch for `==> Done: Completed with exit status 0` on the build. Anything else on
**Events** (a red ✗) is a build failure and the log tail names the missing package or
syntax error. The service URL is `https://<name>.onrender.com` — TLS is automatic,
and it is the URL you paste in the README (Step 9).

---

## 8. Verification checklist — run all of it, don't eyeball it

Copy-paste this; it exercises every role's endpoint on the live URL.

```bash
URL=https://log-search-analyzer.onrender.com     # ← your URL

echo "--- health ---"          && curl -sS $URL/api/health
echo "--- api root (json) ---" && curl -sS -H 'Accept: application/json' $URL/
echo "--- dashboard html ---"  && curl -sS -o /dev/null -w 'status=%{http_code} bytes=%{size_download}\n' -H 'Accept: text/html' $URL/
echo "--- assets ---"          && for p in /css/styles.css /js/app.js /js/api.js /docs; do printf "%-16s " $p; curl -sS -o /dev/null -w 'status=%{http_code}\n' $URL$p; done
echo "--- search ---"          && curl -sS "$URL/api/logs?severity=ERROR&limit=1"
echo "--- trace ---"           && curl -sS "$URL/api/logs?request_id=req-8f3k2" | head -c 300
echo "--- stats ---"           && curl -sS "$URL/api/stats/errors?top=3"
echo "--- summary ---"         && curl -sS "$URL/api/stats/summary"
```

Pass criteria:

- [ ] `/api/health` → `{"status":"ok","db":"ok","total_entries":17,...}` (`0` if you
      disabled seeding; `degraded` means the DB connection is wrong — see Step 11)
- [ ] `/` with a browser `Accept: text/html` → **200 and ~4–5 KB**, not 200 with a few
      hundred bytes of JSON. HTML = frontend found; JSON = it wasn't.
- [ ] `/css/styles.css`, `/js/app.js`, `/js/api.js` → all **200**. Any 404 here is the
      classic "grey, unstyled, buttons do nothing" bug.
- [ ] `/explorer` loads the legacy single-file explorer (fallback page, useful to know exists)
- [ ] `request_id=req-8f3k2` returns the auth-service trace rows (demo step 4)
- [ ] In a browser: **upload `testdata/sample_valid.jsonl`** (create it with
      `python scripts/generate_logs.py` if missing) → expect a `partial` report with
      skipped-line reasons, then filter to `ERROR` and click a recurring-error chip.
- [ ] Invalid uploads still rejected:
      `curl -F "file=@README.md" $URL/api/logs/upload` → `400 Invalid file type…`

Then on the service page: **Health Check Path** is green, and **Metrics** should show
low CPU (512 MB RAM ceiling — a memory kill appears as a restart in **Events**).

---

## 9. Finish: make it count for the grade

- [ ] Put the live URL in the README and at the top of the demo slides, plus
      `Deployed on Render (free tier)` on the architecture slide.
- [ ] Add a one-click re-deploy button so the marker can run it too — under the
      README title (works because `render.yaml` is at the repo root):

      ```markdown
      [![Deploy to Render](https://binaries.render.com/docs/render-button.svg)](https://render.com/deploy?repo=kigbanib/20-log-search-and-analyzer)
      ```

- [ ] Commit the README change and open a PR (`gh pr create`) — don't ship from a
      branch nobody reviewed.
- [ ] Update `README.md` → *📦 Deployment* to link here: `docs/render-deploy.md`.
- [ ] Optional: custom domain (Settings → Custom Domains) — supported on Free; needs a
      CNAME to the service URL. Skip it for a course demo; it adds a
      DNS-propagation way to lose 20 minutes.

---

## 10. Demo-day operations (read this the night before)

- **Cold start ≈ 1 minute.** A free service with no traffic for 15 minutes is spun
  down, and Render shows its own loading page while it boots. **Open the dashboard
  and hit `GET /api/health` ~2 minutes before you start presenting, and keep the tab
  open** — that is the whole trick.
- **Don't make a keep-alive ping your safety net.** Pinging `/api/health` every ~10
  minutes from cron/CI does keep a free service warm, but it doesn't protect you from
  a redeploy wiping the database. If the demo is high-stakes and someone has $7: move
  the service to **Starter** the day before (always-on, no cold starts), downgrade
  afterwards.
- **Free tier is 750 instance-hours per workspace per month.** One always-on free
  service uses ~720, so a single service fits; two can exhaust it and Render
  **suspends all free services in the workspace until the 1st**. Worth knowing if the
  whole team deploys on one account.
- **Practice the failure.** Rehearse the fallback line: "if the URL is down, here is
  the local command" → `uvicorn app.main:app --port 8000` with the same seeded DB.
  Saying it once in rehearsal turns an outage into a "we planned for this" moment.
- **Data resets.** With SQLite: every deploy/spin-down. With Render Free Postgres:
  nothing resets mid-demo, but the DB self-destructs at day 30 — if you demo after
  that, recreate it and re-seed (30 seconds, Step 13).
- **While spun down, `GET /robots.txt` returns a "Disallow all" stub from Render**
  that never reaches your app. If a monitoring script ever reports a suspiciously
  empty 200, check it isn't probing that path.

---

## 11. Troubleshooting — the real failure modes

| Symptom / log line | Cause | Fix |
|---|---|---|
| `==> Port scan timeout reached, no open ports detected.` | Bound to `127.0.0.1`, or a hardcoded `--port 8000`, or a `PORT` env var fighting `$PORT` | Start command must be `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; delete any `PORT` env var |
| `Error loading ASGI app. Could not import module "app.main"` | Wrong module path (`main:app`), or the start command runs from a subdirectory | Keep `app.main:app` (package `app`, object `app`); don't add `cd …` to the start command |
| `ModuleNotFoundError: No module named 'x'` at startup | Dependency missing from `requirements.txt` (Render installs from that file only — your local venv is irrelevant) | Add it, push, redeploy. Also check casing: `App/main.py` ≠ `app/main.py` on Render's Linux FS |
| `ModuleNotFoundError: No module named 'psycopg2'` after setting a Postgres `DATABASE_URL` | Postgres driver not installed | It's in `requirements.txt` now; if your branch predates that, add `psycopg2-binary>=2.9.9` |
| Build fails in pip with resolver/wheel errors | Render's default Python moved to **3.14.8** for new services; your pins target 3.11 | Restore `.python-version` (`3.11`), or set env var `PYTHON_VERSION=3.11.9` (that method needs a **fully qualified** version) |
| Page loads unstyled / `Failed to fetch` in devtools | `/css` or `/js` mount missing (cwd-relative paths, or `frontend/` not committed) | `curl $URL/css/styles.css` must be 200. `app/main.py` now anchors the mounts to the repo root — pull the latest branch if you deployed an old commit |
| `/api/health` → `{"status":"degraded","db":"error"}` | Bad `DATABASE_URL`, DB in a different region, or DB still `Creating` | Paste the **Internal** URL; put service + DB in the same region; confirm the DB is `Available`; restart the service |
| 500 only on the *first* request after an idle period | A restarted/maintained Postgres killed pooled connections | Already mitigated (`pool_pre_ping=True`, `pool_recycle=1800` in `app/database.py`) |
| Upload "succeeds", rows vanish minutes later | Ephemeral filesystem (Step 1) | Use Postgres, or upload immediately before you show that table |
| Service shows `Suspended`, or all free services stop | Monthly 750 free hours exhausted, or a free Postgres hit its 30-day expiry | Wait for the 1st / upgrade one service to Starter / recreate the DB and re-seed |
| Upload rejected near the size limit | The 5 MB cap is enforced in-process *and* in the UI | Change `MAX_UPLOAD_MB` **and** `MAX_UPLOAD_BYTES` in `frontend/js/api.js` together |

If a deploy fails and you need to go back: **Events → ⋯ → Rollback to this commit**
(Free keeps the two most recent deploys). To force a redeploy with no code change:
**Manual Deploy → Deploy latest commit** — that re-runs `init_db` and re-seeds an
empty database.

---

## 12. Trade-offs to be able to state at the demo (rubric: architecture + honesty)

State them as decisions, not apologies:

1. **SQLite for MVP, Postgres as the scaling path.** Zero config, no extra service,
   fine below ~100k rows. The platform's ephemeral filesystem is exactly why
   `init_db` + `SEED_ON_START` exist and why `DATABASE_URL` is an env var rather than
   a constant: swapping to Postgres was one URL + one driver, because `create_engine`
   and the ORM own all dialect-specific behaviour.
2. **Single service, single origin.** FastAPI serves the UI, so there's no second
   deploy, no CORS pre-flight on uploads, one URL in the README. The cost: the same
   free instance serves static assets, so a cold start delays the UI too.
3. **Free tier = ~1 min cold start.** Handled by making `/api/health` the Render
   health check path, so the instance is warm and DB-connected before it takes
   traffic; `pool_pre_ping` covers a DB that restarted underneath us.
4. **5 MB cap enforced in-process** (`app/routers/upload.py` reads the whole body into
   memory). Honest next step: stream to disk/S3 behind an nginx size limit, or chunk.
5. **No auth.** The public URL means anyone can upload to your demo database. On a
   free hobby URL that is an accepted risk for a 7-minute demo; an API-key dependency
   (and Render's `ipAllowList`, which needs a paid workspace) is the fix — it's
   already in Known Limitations.

---

## 13. Local commands you'll actually reuse

```bash
python -m app.seed                # seed only if empty
python -m app.seed --force        # add another demo batch
python scripts/generate_logs.py   # testdata/sample_valid.jsonl (500 lines)
pytest -q                         # 48 tests, no network needed

# Run exactly the way Render does (repo root, no --reload):
uvicorn app.main:app --host 0.0.0.0 --port $PORT

# Exercise the Postgres code path locally (needs a reachable Postgres):
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/logsearch \
  SEED_ON_START=true uvicorn app.main:app --port 8000
```

To wipe a SQLite demo DB and re-seed on Render: **Environment → `SEED_ON_START=true`
→ Manual Deploy → Deploy latest commit** (a fresh build artifact starts with no
`logs.db`, so the seed runs). On Postgres you cannot shell in on the free tier (no
SSH, no one-off jobs), so use the DB's **External connection string** from your laptop:

```bash
psql "postgres://user:pass@dpg-xxxx-a-frankfurt.render.com/logsearch" -c 'delete from log_entries;'
```

(Free Render Postgres has no managed pooler, so `psql` connects directly; if your
network blocks port 5432, use `pgAdmin`/`DBeaver` from home internet, or just restart
the service to re-seed.)

---

## Appendix: live status

Not deployed as of writing — no URL to publish yet. Whoever runs Step 5 fills this in
and PRs it:

| Field | Value |
|---|---|
| Service URL | _pending_ |
| Region | _pending (Frankfurt recommended)_ |
| Compute plan | Free |
| Data store | _SQLite / Render Free Postgres / Neon_ |
| Deployed by | _pending_ |
| Auto-deploy branch | `main` |
