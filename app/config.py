"""
Application configuration for Log Search & Analyzer.
Designed for 7-day MVP with production-readiness for Render deployment.
"""

import os
from pathlib import Path
from typing import Set

# Repo root — used to anchor every relative path so the app behaves identically
# whether it is launched from the repo root (local dev, Render) or from anywhere
# else (systemd, Docker WORKDIR, `uvicorn --app-dir`).
BASE_DIR: Path = Path(__file__).resolve().parent.parent


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_sqlite_url(url: str) -> str:
    """Rewrite a *relative* SQLite path against BASE_DIR.

    `sqlite:///./logs.db` normally resolves against the process working
    directory. On a PaaS that is invisible to you until it silently puts the
    database somewhere else (or you get `unable to open database file`).
    `sqlite:////var/data/logs.db` (4 slashes) is absolute and is left alone —
    that is the form to use with a Render persistent disk.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    path_part = url[len(prefix):]
    if path_part in ("", ":memory:") or path_part.startswith("file:"):
        return url
    candidate = Path(path_part)
    if candidate.is_absolute():
        return url
    return prefix + str((BASE_DIR / candidate).resolve())


# Database Configuration
# Default to a SQLite file in the repo root, override with an env var (e.g. on Render).
# NOTE: Render's filesystem is ephemeral — a SQLite file is wiped on every
# redeploy/restart/spin-down. Set DATABASE_URL to a Postgres URL to persist data.
DATABASE_URL: str = _resolve_sqlite_url(
    os.getenv("DATABASE_URL", "sqlite:///./logs.db")
)

# Heroku/Render-style URLs sometimes use the bare `postgres://` scheme,
# which SQLAlchemy no longer recognises as a Postgres dialect.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_SQLITE: bool = DATABASE_URL.startswith("sqlite")

# Pagination Defaults and Bounds
DEFAULT_PAGE: int = 1
DEFAULT_PAGE_SIZE: int = 50
MAX_PAGE_SIZE: int = 100

# Agreed Team Log Severities
VALID_SEVERITIES: Set[str] = {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}

# Upload limits (env-driven per teamguide)
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "5"))
MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

# CORS / Deployment
CORS_ORIGIN: str = os.getenv("CORS_ORIGIN", "*")
PORT: int = int(os.getenv("PORT", "8000"))

# Demo seeding. When enabled, startup seeds the demo dataset *only if* the
# database is empty, so a freshly deployed (or freshly wiped) instance never
# shows an empty dashboard. Defaults to on under Render (Render sets RENDER=1)
# and off everywhere else, so local dev and the test suite stay untouched.
_seed_default = "true" if os.getenv("RENDER") else "false"
SEED_ON_START: bool = _truthy(os.getenv("SEED_ON_START", _seed_default))
