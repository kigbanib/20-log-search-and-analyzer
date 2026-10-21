"""Unit tests for the log parser.

Each test maps to a rule in docs/log-format.md. If a test fails, either the
parser has a bug or the spec changed — do not adjust the test to match the code
without updating the spec first.
"""

from datetime import datetime, timezone

import pytest

from app.parser.parser import parse_line, parse_lines
from app.parser.schema import (
    ALLOWED_SEVERITIES,
    ParseError,
    ParsedLog,
)


# Helper: a known-good line, so tests focus on the field under test.
def valid_line(**overrides) -> str:
    """Return a valid JSONL line, with optional field overrides."""
    base = {
        "timestamp": "2026-10-20T10:15:04Z",
        "severity": "ERROR",
        "service": "auth-service",
        "request_id": "req-8f3k2",
        "message": "Database connection timeout",
    }
    base.update(overrides)
    import json

    return json.dumps(base)


# --- 1. Happy path -------------------------------------------------------


def test_valid_line_parses_to_parsedlog():
    """The canonical example from docs/log-format.md must parse."""
    result = parse_line(valid_line(), line_no=1)

    assert isinstance(result, ParsedLog)
    assert result.severity == "ERROR"
    assert result.service == "auth-service"
    assert result.request_id == "req-8f3k2"
    assert result.message == "Database connection timeout"


# --- 2. Timestamp rules --------------------------------------------------


def test_missing_timestamp_is_parse_error():
    line = valid_line()
    import json

    obj = json.loads(line)
    del obj["timestamp"]

    result = parse_line(json.dumps(obj), line_no=1)

    assert isinstance(result, ParseError)
    assert "timestamp" in result.reason


def test_timestamp_is_timezone_aware_utc():
    result = parse_line(valid_line(), line_no=1)

    assert isinstance(result, ParsedLog)
    assert result.timestamp.tzinfo is not None
    assert result.timestamp.utcoffset() == timezone.utc.utcoffset(None)
    assert result.timestamp == datetime(2026, 10, 20, 10, 15, 4, tzinfo=timezone.utc)


# --- 3. Severity rules ---------------------------------------------------


def test_lowercase_severity_is_normalized_to_uppercase():
    result = parse_line(valid_line(severity="error"), line_no=1)

    assert isinstance(result, ParsedLog)
    assert result.severity == "ERROR"


def test_unknown_severity_is_parse_error_with_line_number():
    result = parse_line(valid_line(severity="FATAL"), line_no=7)

    assert isinstance(result, ParseError)
    assert result.line_no == 7
    assert "FATAL" in result.reason


# --- 4. request_id is optional -------------------------------------------


def test_missing_request_id_is_stored_as_none():
    line = valid_line()
    import json

    obj = json.loads(line)
    del obj["request_id"]

    result = parse_line(json.dumps(obj), line_no=1)

    assert isinstance(result, ParsedLog)
    assert result.request_id is None


def test_null_request_id_is_stored_as_none():
    result = parse_line(valid_line(request_id=None), line_no=1)

    assert isinstance(result, ParsedLog)
    assert result.request_id is None


# --- 5. Garbage input ----------------------------------------------------


def test_garbage_line_is_parse_error_not_exception():
    result = parse_line("this is not json", line_no=3)

    assert isinstance(result, ParseError)
    assert result.line_no == 3
    assert "invalid JSON" in result.reason


# --- 6. Batch behavior (skip-and-report) ---------------------------------


def test_batch_mixed_lines_separates_parsed_from_errors():
    lines = [
        valid_line(),        # line 1: valid
        "garbage",           # line 2: error
        "",                  # line 3: error (empty)
        valid_line(),        # line 4: valid
    ]

    parsed, errors = parse_lines(lines)

    assert len(parsed) == 2
    assert len(errors) == 2
    assert {e.line_no for e in errors} == {2, 3}


def test_empty_file_returns_empty_lists():
    parsed, errors = parse_lines([])

    assert parsed == []
    assert errors == []


# --- 7. The major failure path (30% garbage) -----------------------------


def test_batch_with_30_percent_garbage_does_not_crash():
    """This is the 'major failure path' required by the rubric.

    Real logs are partly corrupt. We must ingest the good 70% and report
    the bad 30% cleanly — never crash, never lose the good lines.
    """
    good_line = valid_line()
    garbage_line = "{broken json"

    # 100 lines: 70 good, 30 garbage, shuffled so garbage isn't grouped.
    lines: list[str] = []
    for i in range(100):
        if i % 10 < 3:            # 30% garbage
            lines.append(garbage_line)
        else:
            lines.append(good_line)

    parsed, errors = parse_lines(lines)

    assert len(parsed) == 70
    assert len(errors) == 30
    # Line numbers must be preserved for every error.
    assert all(e.line_no >= 1 for e in errors)
    # Every successful parse carries the full schema.
    assert all(isinstance(p, ParsedLog) for p in parsed)


# --- 8. Allowed severities are exactly the five in the spec -------------


def test_allowed_severities_set_is_correct():
    assert ALLOWED_SEVERITIES == {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}