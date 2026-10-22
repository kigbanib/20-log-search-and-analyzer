"""
FastAPI router for Log Search and Filter API.
Provides GET /api/logs conforming to the agreed team API specification.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    VALID_SEVERITIES,
)
from app.database import get_db
from app.deps import get_owner
from app.crud import get_logs
from app.schemas import PaginatedLogsResponse, ErrorResponse

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get(
    "",
    response_model=PaginatedLogsResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters (e.g. invalid severity or date range)"},
        422: {"description": "Unprocessable query parameter (e.g. invalid date format or out-of-bounds pagination)"},
    },
    summary="Search and filter log entries",
    description=(
        "Retrieve paginated log entries with optional filters for severity, "
        "request ID, and time range. Results are ordered predictably by timestamp descending, "
        "with ID descending as a deterministic tie-breaker."
    ),
)
def list_logs(
    severity: Optional[str] = Query(
        None,
        description="Filter by severity level (DEBUG, INFO, WARN, ERROR, CRITICAL). Case-insensitive.",
        examples=["ERROR", "warn"],
    ),
    request_id: Optional[str] = Query(
        None,
        description="Filter by exact correlation/request ID. Partial matching is not permitted.",
        examples=["req-8f3k2"],
    ),
    from_time: Optional[datetime] = Query(
        None,
        alias="from",
        description="Start of date range in ISO-8601 format (inclusive).",
        examples=["2026-10-20T00:00:00Z"],
    ),
    to_time: Optional[datetime] = Query(
        None,
        alias="to",
        description="End of date range in ISO-8601 format (inclusive).",
        examples=["2026-10-20T23:59:59Z"],
    ),
    page: int = Query(
        DEFAULT_PAGE,
        ge=1,
        description="Page number (1-indexed). Must be >= 1.",
    ),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Page size limit. Must be between 1 and {MAX_PAGE_SIZE}.",
    ),
    db: Session = Depends(get_db),
    owner: str = Depends(get_owner),
):
    """
    Search and filter logs with validated parameters and pagination.
    Session-scoped: only the caller's rows + the shared anonymous bucket.
    """
    # 1. Validate severity against agreed allowed values
    if severity is not None and severity.strip():
        norm_severity = severity.strip().upper()
        if norm_severity not in VALID_SEVERITIES:
            allowed_list = ", ".join(sorted(VALID_SEVERITIES))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity '{severity}'. Allowed values are: {allowed_list}.",
            )
        severity = norm_severity

    # 2. Validate date range logical ordering
    if from_time is not None and to_time is not None:
        if from_time > to_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The 'from' parameter must be earlier than or equal to the 'to' parameter.",
            )

    # 3. Fetch matching logs and total count from database (session-scoped)
    total, entries = get_logs(
        db=db,
        severity=severity,
        request_id=request_id,
        from_time=from_time,
        to_time=to_time,
        page=page,
        limit=limit,
        owner=owner,
    )

    # 4. Return paginated response complying with team contract
    return PaginatedLogsResponse(
        total=total,
        page=page,
        limit=limit,
        entries=entries,
    )
