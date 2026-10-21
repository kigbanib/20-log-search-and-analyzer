"""Upload endpoint for Log Search & Analyzer.

Owner: Ingestion & Parser Lead (Role 1)
Depends on: app.services.ingestion (parser + DB) + app.database.get_db

Contract: POST /api/logs/upload  multipart field name `file`
-> 200 (even with skipped lines) or 400 (empty/unreadable/oversized)
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import MAX_UPLOAD_BYTES, MAX_UPLOAD_MB
from app.database import get_db
from app.services.ingestion import process_upload

router = APIRouter(prefix="/api/logs", tags=["Ingestion"])


@router.post("/upload", summary="Upload a JSONL log file")
async def upload_log_file(
    file: UploadFile = File(..., description="Log file (.log, .jsonl, .txt)"),
    db: Session = Depends(get_db),
):
    # 1. Validate file extension (case-insensitive)
    filename = file.filename or "upload.log"
    if not filename.lower().endswith((".log", ".jsonl", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a .log, .jsonl, or .txt file.",
        )

    # 2. Read file and enforce size limit
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size is {MAX_UPLOAD_MB} MB.",
        )

    if not file_bytes or not file_bytes.strip():
        raise HTTPException(status_code=400, detail="File is empty.")

    # 3. Process (parse + store + build response)
    return process_upload(file_bytes, filename, db)
