"""
Main FastAPI application entry point for Log Search & Analyzer.

Integrates all 5 roles:
- Role 1 (Ingestion & Parser): POST /api/logs/upload
- Role 2 (Search & Filter): GET /api/logs
- Role 3 (Analytics & Monitoring): GET /api/stats/* + GET /api/health
- Role 4 (Dashboard): serves frontend at / + /explorer + static assets
- Role 5 (QA & DevOps): lifespan init_db, seed, health

Single-deploy design: ONE FastAPI serves API + frontend (no CORS split).
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, CORS_ORIGIN, SEED_ON_START
from app.database import SessionLocal, init_db
from app.routers import analytics, logs, upload

# Use uvicorn's own logger: `uvicorn` only configures handlers/levels for the
# "uvicorn.*" loggers, so an app-namespaced logger's INFO lines are swallowed
# and startup diagnostics never reach Render's runtime logs.
logger = logging.getLogger("uvicorn.error")

# ---- Static asset locations (anchored to the repo root, not the process cwd) ----
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_DIR = BASE_DIR / "static"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
LEGACY_INDEX = STATIC_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure DB tables exist on startup, then seed demo data if the DB is empty.

    Seeding is opt-in (SEED_ON_START, on by default under Render) and must never
    take the service down: a failed seed is logged and the API still serves.
    """
    init_db()
    if SEED_ON_START:
        try:
            from app.seed import seed_demo_data_if_empty

            db = SessionLocal()
            try:
                inserted = seed_demo_data_if_empty(db)
                if inserted:
                    logger.info("Seeded %s demo log entries (empty database).", inserted)
            finally:
                db.close()
        except Exception as exc:  # pragma: no cover - defensive, never block boot
            logger.warning("Demo seed skipped: %s", exc)
    yield


app = FastAPI(
    title="Log Search & Analyzer API",
    description=(
        "Mini log-analysis backend inspired by Splunk and Datadog. "
        "Provides high-performance search, filtering, and pagination over structured log entries."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — env-driven, defaults to * for MVP
_origins = [o.strip() for o in CORS_ORIGIN.split(",")] if CORS_ORIGIN != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- API Routers (order matters: specific before generic) ----
app.include_router(upload.router)      # POST /api/logs/upload
app.include_router(logs.router)        # GET /api/logs
app.include_router(analytics.router)   # GET /api/stats/* + GET /api/health


# ---- Static assets (legacy `static/` from Role 2 + modern `frontend/` from Role 4) ----
# Absolute paths on purpose: a cwd-relative `directory="static"` silently
# skips the mount (404 CSS/JS, unstyled dashboard) whenever the app is started
# from another working directory.
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Frontend (Role 4) — mount css/js directories so relative href="css/..." resolves
if (FRONTEND_DIR / "css").is_dir():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="frontend_css")
if (FRONTEND_DIR / "js").is_dir():
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="frontend_js")


def _frontend_index_exists() -> bool:
    return FRONTEND_INDEX.is_file()


def _legacy_index_exists() -> bool:
    return LEGACY_INDEX.is_file()


@app.get("/explorer", tags=["UI"], summary="Interactive Log Explorer")
def explorer():
    """Serves the dashboard (frontend takes precedence over legacy static)."""
    if _frontend_index_exists():
        return FileResponse(str(FRONTEND_INDEX))
    if _legacy_index_exists():
        return FileResponse(str(LEGACY_INDEX))
    return {"message": "Frontend not built — run frontend build or check static/"}


@app.get("/dashboard", tags=["UI"], include_in_schema=False)
def dashboard():
    return explorer()


@app.get("/", tags=["Root"], summary="API Root / Dashboard")
def root(request: Request):
    """
    API discovery when Accept: application/json, otherwise serve dashboard.
    Browsers send text/html, API clients (TestClient, curl with JSON) get JSON.
    """
    accept = request.headers.get("accept", "")
    # Only serve HTML if client explicitly asks for it (browser)
    # TestClient defaults to */* and must get JSON for contract tests
    wants_html = "text/html" in accept
    wants_json = "application/json" in accept
    # If explicitly wants HTML and not JSON, serve frontend
    if wants_html and not wants_json:
        if _frontend_index_exists():
            return FileResponse(str(FRONTEND_INDEX))
        if _legacy_index_exists():
            return FileResponse(str(LEGACY_INDEX))

    return {
        "name": "Log Search & Analyzer API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "explorer_url": "/explorer",
        "frontend_url": "/" if _frontend_index_exists() else None,
        "endpoints": {
            "upload_logs": "POST /api/logs/upload",
            "search_logs": "GET /api/logs?severity=&request_id=&from=&to=&page=&limit=",
            "error_stats": "GET /api/stats/errors?top=",
            "summary": "GET /api/stats/summary",
            "health": "GET /api/health",
            "search_logs_alias": "/api/logs",  # for test compatibility
        },
    }
