"""Line-by-line parser for JSONL log files.

Two public functions:

    parse_line(line, line_no)  -> ParsedLog | ParseError
    parse_lines(lines)          -> (list[ParsedLog], list[ParseError])

The parser NEVER raises on bad input. A bad line becomes a ParseError value
which the caller can report to the user. This is the "skip-and-report" policy
described in docs/log-format.md.

See docs/log-format.md for the full field specification.
"""

import json
from datetime import datetime, timezone

from app.parser.schema import (
    ALLOWED_SEVERITIES,
    ParseError,
    ParsedLog,
)


def parse_line(line: str, line_no: int) -> ParsedLog | ParseError:
    """Parse a single line of a JSONL file.

    Returns ParsedLog on success, ParseError on failure.
    Never raises.
    """
    raw = line.rstrip("\n")
    stripped = raw.strip()

    # Blank / whitespace-only lines are ignored, not counted as errors.
    # Caller decides whether to skip silently or report; here we report as
    # an error but with a reason the ingestion layer can choose to filter.
    if not stripped:
        return ParseError(line_no, "empty line", raw)

    # --- JSON structure ---
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return ParseError(line_no, f"invalid JSON: {exc.msg}", raw)

    if not isinstance(obj, dict):
        return ParseError(line_no, "line is not a JSON object", raw)

    # --- timestamp ---
    ts_raw = obj.get("timestamp")
    if not isinstance(ts_raw, str) or not ts_raw.strip():
        return ParseError(line_no, "missing or invalid 'timestamp'", raw)
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except ValueError:
        return ParseError(line_no, f"timestamp not ISO-8601: {ts_raw!r}", raw)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)

    # --- severity ---
    sev_raw = obj.get("severity")
    if not isinstance(sev_raw, str) or not sev_raw.strip():
        return ParseError(line_no, "missing 'severity'", raw)
    severity = sev_raw.strip().upper()
    if severity not in ALLOWED_SEVERITIES:
        return ParseError(line_no, f"unknown severity {sev_raw!r}", raw)

    # --- service ---
    service = obj.get("service")
    if not isinstance(service, str) or not service.strip():
        return ParseError(line_no, "missing or empty 'service'", raw)
    service = service.strip()

    # --- request_id (optional) ---
    request_id = obj.get("request_id")
    if request_id is not None:
        if not isinstance(request_id, str) or not request_id.strip():
            return ParseError(line_no, "invalid 'request_id'", raw)
        request_id = request_id.strip()

    # --- message ---
    message = obj.get("message")
    if not isinstance(message, str) or not message.strip():
        return ParseError(line_no, "missing or empty 'message'", raw)
    message = message.strip()

    return ParsedLog(ts, severity, service, request_id, message)


def parse_lines(lines: list[str]) -> tuple[list[ParsedLog], list[ParseError]]:
    """Parse an iterable of lines. Returns (parsed, errors).

    Line numbers are 1-based to match how users read files in an editor.
    """
    parsed: list[ParsedLog] = []
    errors: list[ParseError] = []
    for i, line in enumerate(lines, start=1):
        result = parse_line(line, i)
        if isinstance(result, ParseError):
            errors.append(result)
        else:
            parsed.append(result)
    return parsed, errors