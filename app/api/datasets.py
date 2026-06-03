import os
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException

from app.services.upload_service import upload_dataset_service

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


@router.post("/{name}")
async def load_sample_dataset(name: str):
    """
    Loads a pre-built sample dataset by name and runs it through
    the normal upload pipeline — returns dataset_id + suggestions.
    """
    filename = SAMPLE_REGISTRY.get(name)

    if not filename:
        raise HTTPException(
            status_code=404,
            detail=f"Sample '{name}' not found. Available: {list(SAMPLE_REGISTRY.keys())}"
        )

    file_path = SAMPLES_DIR / filename

    if not file_path.exists():
        logger.error(f"Sample file not found on disk: {file_path}")
        raise HTTPException(
            status_code=500,
            detail=f"Sample file '{filename}' not found on server."
        )

    logger.info(f"Loading sample dataset: {name} → {filename}")

    # Wrap as a file-like object matching FastAPI's UploadFile interface
    class FakeUploadFile:
        def __init__(self, path: Path):
            self.filename = path.name
            self._contents = path.read_bytes()

        async def read(self) -> bytes:
            return self._contents

    fake_file = FakeUploadFile(file_path)
    result = await upload_dataset_service(fake_file)

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    return result