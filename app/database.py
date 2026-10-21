"""
Database setup, connection pooling, and session lifecycle management.
Uses SQLAlchemy 2.0+ standard practices.
"""

from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import DATABASE_URL, IS_SQLITE

# Engine Configuration
is_sqlite = IS_SQLITE
# `timeout` (seconds) is the sqlite3 driver's busy limit: without it two
# concurrent requests writing to the same SQLite file raise "database is locked".
connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}

engine_kwargs = {
    "connect_args": connect_args,
    "echo": False,  # Set to True for verbose SQL query logging during debugging
}
if not is_sqlite:
    # A managed Postgres (e.g. Render Free) can restart or drop idle
    # connections at any time. pre_ping validates a connection before use and
    # recycle bounds how long one may sit in the pool, so a stale socket turns
    # into a silent reconnect instead of a 500 for the user.
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 1800

engine = create_engine(DATABASE_URL, **engine_kwargs)

# Enable Foreign Key enforcement in SQLite (SQLite disables foreign keys by default)
if is_sqlite:
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Session Factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Declarative Base for Models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per HTTP request
    and guarantees proper closure upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Creates all database tables defined in models."""
    Base.metadata.create_all(bind=engine)
