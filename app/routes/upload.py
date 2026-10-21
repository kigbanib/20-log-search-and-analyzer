from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.ingestion import process_upload

router = APIRouter()

# Set the max file size to 5 MB (matching docs/log-format.md if we specify there)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.post("/api/logs/upload")
async def upload_log_file(file: UploadFile = File(...)):
    # 1. Validate file extension
    if not file.filename.endswith((".log", ".jsonl", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a .log, .jsonl, or .txt file.",
        )

    # 2. Read file and enforce size limit
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    if not file_bytes:
        raise HTTPException(status_code=400, detail="File is empty.")

    # 3. Process
    return process_upload(file_bytes, file.filename)