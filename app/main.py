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
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGIN
from app.database import init_db
from app.routers import analytics, logs, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure DB tables exist on startup (and seed if empty — optional)."""
    init_db()
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
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Frontend (Role 4) — mount css/js directories so relative href="css/..." resolves
if os.path.exists("frontend/css"):
    app.mount("/css", StaticFiles(directory="frontend/css"), name="frontend_css")
if os.path.exists("frontend/js"):
    app.mount("/js", StaticFiles(directory="frontend/js"), name="frontend_js")


def _frontend_index_exists() -> bool:
    return os.path.exists("frontend/index.html")


def _legacy_index_exists() -> bool:
    return os.path.exists("static/index.html")


@app.get("/explorer", tags=["UI"], summary="Interactive Log Explorer")
def explorer():
    """Serves the dashboard (frontend takes precedence over legacy static)."""
    if _frontend_index_exists():
        return FileResponse("frontend/index.html")
    if _legacy_index_exists():
        return FileResponse("static/index.html")
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
            return FileResponse("frontend/index.html")
        if _legacy_index_exists():
            return FileResponse("static/index.html")

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
