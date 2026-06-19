import logging
import asyncio
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from app.services.upload_stream_service import upload_dataset_stream
from app.core.auth import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter()

SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"

SAMPLE_REGISTRY = {
    "household":  "household_expenses.csv",
    "investment": "investment_portfolio.csv",
    "retail":     "retail_sales.csv",
    "hr":         "hr_employee_analytics.csv",
    "health":     "health_fitness_tracker.csv",
    "restaurant": "restaurant_analytics.csv",
}

_job_store: dict[str, dict] = {}
_JOB_TTL_SECONDS = 60


# Phase 1: authenticated — validate, load file, return job_id
@router.get("/{name}")
async def load_sample_dataset(
    name: str,
    user_id: str = Depends(get_current_user_id),
):
    filename = SAMPLE_REGISTRY.get(name)
    if not filename:
        raise HTTPException(status_code=404, detail=f"Sample '{name}' not found.")

    file_path = SAMPLES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=500, detail="Sample file not found on server.")

    contents = file_path.read_bytes()
    logger.info(f"Sample '{name}' requested by user {user_id}")

    job_id = str(uuid.uuid4())
    _job_store[job_id] = {"filename": filename, "contents": contents, "user_id": user_id}

    async def _cleanup():
        await asyncio.sleep(_JOB_TTL_SECONDS)
        _job_store.pop(job_id, None)

    asyncio.create_task(_cleanup())

    return {"job_id": job_id}


# Phase 2: unauthenticated SSE stream (EventSource can't send headers)
@router.get("/stream/{job_id}")
async def stream_sample_dataset(job_id: str):
    job = _job_store.pop(job_id, None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    async def event_generator():
        async for event in upload_dataset_stream(
            job["filename"], job["contents"], user_id=job["user_id"]
        ):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )