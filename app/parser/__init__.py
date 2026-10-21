"""Parser package — re-exports for convenience."""
from app.parser.parser import parse_line, parse_lines
from app.parser.schema import ALLOWED_SEVERITIES, ParsedLog, ParseError

__all__ = ["parse_line", "parse_lines", "ParsedLog", "ParseError", "ALLOWED_SEVERITIES"]
