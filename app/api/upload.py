import uuid
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.services.upload_service import upload_dataset_service
from app.services.upload_stream_service import upload_dataset_stream

logger = logging.getLogger(__name__)

router = APIRouter()

# ── In-memory job store ───────────────────────────────────────────────────────
# Stores raw file bytes temporarily between /start and /stream
# Key: job_id, Value: {"filename": str, "contents": bytes}
_job_store: dict[str, dict] = {}
_JOB_TTL_SECONDS = 60  # jobs expire after 60s if stream never connects


# ── Original route (kept for backwards compatibility) ─────────────────────────
@router.post("/")
async def upload_dataset(file: UploadFile = File(...)):
    result = await upload_dataset_service(file)
    return result


# ── Phase 1: Accept file, store in memory, return job_id ─────────────────────
@router.post("/start")
async def upload_start(file: UploadFile = File(...)):
    """
    Accepts the uploaded file, stores bytes in memory, returns a job_id.
    The client then opens GET /upload/stream/{job_id} to get SSE progress.
    """
    filename = file.filename or ""

    if not filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(
            status_code=400,
            detail="Only CSV or Excel files supported"
        )

    contents = await file.read()

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds 10 MB limit"
        )

    job_id = str(uuid.uuid4())
    _job_store[job_id] = {
        "filename": filename,
        "contents": contents,
    }

    # Auto-cleanup after TTL
    async def _cleanup():
        await asyncio.sleep(_JOB_TTL_SECONDS)
        _job_store.pop(job_id, None)
        logger.debug(f"Job {job_id} expired and cleaned up")

    asyncio.create_task(_cleanup())

    logger.info(f"Job {job_id} created for file: {filename} ({len(contents)} bytes)")

    return {"job_id": job_id}


# ── Phase 2: Stream SSE progress for a job ────────────────────────────────────
@router.get("/stream/{job_id}")
async def upload_stream(job_id: str):
    """
    Opens an SSE stream and runs the full upload pipeline,
    emitting progress events at each step.
    """
    job = _job_store.get(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found or expired. Please re-upload your file."
        )

    filename = job["filename"]
    contents = job["contents"]

    # Remove from store — single use
    _job_store.pop(job_id, None)

    async def event_generator():
        async for event in upload_dataset_stream(filename, contents):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disables Nginx buffering on Render
            "Connection": "keep-alive",
        },
    )