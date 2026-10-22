"""
Pydantic data validation and serialization schemas for Log Search & Analyzer.
Enforces the agreed API contract across all 5 roles.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_serializer


class SeverityEnum(str, Enum):
    """Agreed severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogEntryResponse(BaseModel):
    """
    Schema for a single log entry in the API response.
    Exact contract agreed with Role 4 (Dashboard) and Role 3 (Analytics).
    """
    id: int = Field(..., description="Unique entry ID")
    timestamp: datetime = Field(..., description="Timestamp of the log event in ISO-8601 format")
    severity: str = Field(..., description="Log severity (DEBUG, INFO, WARN, ERROR, CRITICAL)")
    service: str = Field(..., description="Service name that emitted the log")
    request_id: Optional[str] = Field(None, description="Correlation or request trace ID, if present")
    message: str = Field(..., description="The log message payload")

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        """Always emit ISO-8601 with an explicit UTC marker ('Z').

        SQLite stores naive datetimes (tz dropped on write). Without the 'Z',
        browsers interpret the timestamp as *local* time and the table shows
        wrong hours — so we declare it UTC here.
        """
        return value.isoformat() if value.tzinfo else value.isoformat() + "Z"


class PaginatedLogsResponse(BaseModel):
    """
    Paginated response schema for GET /api/logs.
    Complies with the agreed team API contract:
    {
        "total": 120,
        "page": 1,
        "limit": 50,
        "entries": [...]
    }
    """
    total: int = Field(..., description="Total count of matching records before pagination")
    page: int = Field(..., description="Current page number (1-indexed)")
    limit: int = Field(..., description="Current page size limit")
    entries: List[LogEntryResponse] = Field(..., description="List of log entries for this page")

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Standardized API error response format."""
    detail: str = Field(..., description="Detailed description of the error")


# Integration Schemas for Role 1 (Ingestion)
class UploadBase(BaseModel):
    filename: str
    total_lines: int = 0
    parsed_lines: int = 0
    failed_lines: int = 0
    status: str = "pending"


class UploadCreate(UploadBase):
    pass


class UploadResponse(UploadBase):
    id: int
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)
