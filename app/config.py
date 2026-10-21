"""
Application configuration for Log Search & Analyzer.
Designed for 7-day MVP with production-readiness for Render deployment.
"""

import os
from typing import Set

# Database Configuration
# Default to SQLite local file, override with environment variable (e.g. on Render)
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./logs.db")

# SQLite URLs in Render/Heroku sometimes start with postgres:// instead of postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Pagination Defaults and Bounds
DEFAULT_PAGE: int = 1
DEFAULT_PAGE_SIZE: int = 50
MAX_PAGE_SIZE: int = 100

# Agreed Team Log Severities
VALID_SEVERITIES: Set[str] = {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}
