"""Data shapes produced by the log parser.

These two dataclasses are the public contract between the parser (this module)
and every downstream consumer (ingestion service, API routes, tests).

See docs/log-format.md for the full specification. Do not change the fields
here without sign-off from the Search & Filter API Lead (Role 2).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# The only severities the parser accepts (after uppercasing the input).
ALLOWED_SEVERITIES: frozenset[str] = frozenset(
    {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}
)


@dataclass(frozen=True)
class ParsedLog:
    """A single successfully parsed log line, ready to be stored."""

    timestamp: datetime        # timezone-aware, UTC
    severity: str              # one of ALLOWED_SEVERITIES
    service: str               # non-empty
    request_id: Optional[str]  # None if the line had no request_id
    message: str               # non-empty


@dataclass(frozen=True)
class ParseError:
    """A single line that could not be parsed. Never raised, always returned."""

    line_no: int   # 1-based line number in the uploaded file
    reason: str    # human-readable, safe to show in the UI
    raw: str       # the original line, for display / debugging