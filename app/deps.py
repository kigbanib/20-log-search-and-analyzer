"""Shared request-scoped dependencies (session ownership).

Why this exists: the deployed site serves MANY strangers from ONE database,
so without scoping, anyone who uploads a file leaks their logs to every other
visitor. The dashboard tags every request with a random X-Session-Id header
(stored in the browser's localStorage); uploaded rows inherit that owner id,
and every read endpoint returns the caller ONLY:
  1. rows they own themselves, plus
  2. the shared anonymous bucket (owner == "") — seeded demo data and
     headerless curl uploads live there on purpose.

This is deliberately NOT authentication — anyone who knows a session id could
read it. It is a privacy wall between casual visitors, not a security
boundary. Header value is only ever used as a bound SQL parameter, never
string-interpolated into queries.
"""

from fastapi import Request

from app.models import LogEntry, Upload

ANONYMOUS = ""  # shared bucket: seeds, headerless curl uploads, legacy rows


def get_owner(request: Request) -> str:
    """Anonymous session identity from the X-Session-Id header.

    Missing/blank header -> shared anonymous bucket (""), which keeps curl,
    the test suite, and teammates' scripts working with zero changes.
    Truncated to the column width (64) defensively.
    """
    return (request.headers.get("x-session-id") or ANONYMOUS).strip()[:64]


def visible_entries(owner: str):
    """WHERE fragment: LogEntry rows visible to `owner` (theirs + shared)."""
    return LogEntry.owner.in_((owner, ANONYMOUS))


def visible_uploads(owner: str):
    """WHERE fragment: Upload rows visible to `owner` (theirs + shared)."""
    return Upload.owner.in_((owner, ANONYMOUS))
