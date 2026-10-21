# Frontend — Log Search & Analyzer (Role 4)

Plain HTML/CSS/JS. No build step, no dependencies. Currently runs in **mock
mode** — fully clickable before the backend exists.

## Run it

Any of these:

```bash
# option 1: any static server
cd frontend
python3 -m http.server 8000
# → http://localhost:8000

# option 2: just open index.html in a browser (mock mode needs no server)

# option 3: VS Code "Live Server" extension
```

## Project layout

```
frontend/
├── index.html        # the single page: upload · filters+table · recurring errors
├── css/styles.css    # all styling (severity badge colors live here)
└── js/
    ├── mock.js       # synthetic in-memory dataset (delete after integration)
    ├── api.js        # ← THE INTEGRATION SEAM: all backend calls go through here
    └── app.js        # UI wiring + loading/empty/error/data states
```

## The golden rule: `js/api.js` is the only file that knows about the backend

- `USE_MOCK = true` → calls resolve from the in-memory dataset in `mock.js`
  (with fake latency so loading states are visible).
- `USE_MOCK = false` → calls hit the FastAPI backend using the shapes in
  `docs/api-contract.md`.

**Day 4 integration:** set `USE_MOCK = false` in `js/api.js` (top of file).
If anything breaks beyond that, the API contract drifted — raise it with
Roles 1–3; do NOT patch it silently in the UI.

## Deployment plan (one deploy, no CORS)

FastAPI will serve this folder as static files at the same origin as the API
(Role 5 sets this up on Render). Because it's same-origin, `API_BASE = ""`
just works and we avoid CORS entirely.
If we ever serve the UI separately (e.g. Vercel), set
`API_BASE = "https://<backend>.onrender.com"` and the backend must enable
CORS for that origin.

## Implemented checklist

- [x] Upload form with file picker, size pre-check (5 MB), and the parsed/
      skipped-lines report (per-line errors listed)
- [x] Severity filter, request-ID search (Enter or Apply), date range, pagination
- [x] Recurring-errors panel: click card → severity filter; click request-ID
      chip → trace that request
- [x] Loading / empty / error / data states on every panel
- [x] Health badge in header (total entries; red if API down)
- [x] XSS-safe rendering (`esc()` on all server-provided text)

## Demo flow this UI is designed for

1. Upload a file → show the partial report (skipped lines visible).
2. Severity dropdown → ERROR.
3. Click a `req-…` chip in recurring errors → table traces that request.
4. Point at the header badge: "237 entries, API healthy."

## Running the tests

```bash
node tests/api.test.js      # from the frontend/ folder — pure Node, no deps
```

Covers the contract's happy paths (pagination, severity filter, request-ID
trace, date range, stats, upload) and the required major failure paths
(oversized file, empty file, no matches). After Day 4, the same expectations
get pointed at the real backend.

## Frontend day-by-day (from the team guide)

- D2: upload form + table rendering (done in this scaffold — refine & style)
- D3: filters, request-ID search, recurring-errors panel, all states
- D4: flip `USE_MOCK`, sit with Role 2, fix contract mismatches
- D5: edge cases, 30-second cold-start loading patience, polish
- D6: deploy with Role 5, screenshots for the README
