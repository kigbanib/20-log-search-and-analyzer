"""
Main FastAPI application entry point for Log Search & Analyzer.
Coordinates routers, database initialization, and static assets.
"""

from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Ensures database tables exist on startup.
    """
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

# CORS configuration to allow Role 4 Dashboard to make browser requests smoothly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(logs.router)

# Mount static folder if it exists
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/api/health", tags=["Health"], summary="Service health check")
def health_check():
    """Health check endpoint for Render deployment and monitoring (Role 5)."""
    return {
        "status": "ok",
        "service": "Log Search & Analyzer",
        "version": "1.0.0",
    }


@app.get("/explorer", tags=["UI"], summary="Interactive Log Explorer Web Interface")
def explorer():
    """Serves the interactive Log Explorer web dashboard for manual testing."""
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "Explorer HTML file not found."}


@app.get("/", tags=["Root"], summary="API Root / Overview")
def root(request: Request):
    """
    API root directory.
    Returns JSON API discovery links, or renders explorer UI if accessed via web browser.
    """
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        if os.path.exists("static/index.html"):
            return FileResponse("static/index.html")

    return {
        "name": "Log Search & Analyzer API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "explorer_url": "/explorer",
        "endpoints": {
            "search_logs": "/api/logs",
            "health": "/api/health",
            "explorer": "/explorer",
        },
    }
