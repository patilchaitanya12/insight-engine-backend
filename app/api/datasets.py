import os
import logging
from pathlib import Path
from fastapi.responses import StreamingResponse
from fastapi import APIRouter, HTTPException

from app.services.upload_stream_service import upload_dataset_stream

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Sample dataset registry ───────────────────────────────────────────────────
SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"

SAMPLE_REGISTRY = {
    "household":  "household_expenses.csv",
    "investment": "investment_portfolio.csv",
    "retail":     "retail_sales.csv",
    "hr":         "hr_employee_analytics.csv",
    "health":     "health_fitness_tracker.csv",
    "restaurant": "restaurant_analytics.csv",
}


@router.get("/{name}")
async def load_sample_dataset(name: str):
    """
    Loads a pre-built sample dataset by name and runs it through
    the normal upload pipeline — returns dataset_id + suggestions.
    """
    filename = SAMPLE_REGISTRY.get(name)
    if not filename:
        raise HTTPException(status_code=404, detail=f"Sample '{name}' not found.")

    file_path = SAMPLES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=500, detail=f"Sample file not found on server.")

    contents = file_path.read_bytes()

    async def event_generator():
        async for event in upload_dataset_stream(filename, contents):
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