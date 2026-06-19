import uuid
import asyncio
import json
import logging
import time
import sys
from io import BytesIO
from datetime import datetime
from typing import AsyncGenerator

import pandas as pd

from app.core.database import db
from app.services.schema_analyzer import analyze_schema
from app.services.question_suggester import generate_question_suggestions
from app.utils.schema_builder import build_schema_context
from app.services.llm.factory import get_llm_provider

logger = logging.getLogger("upload_stream_service")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [upload_stream] %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

LLM_TIMEOUT_SECONDS = 15.0
DB_TIMEOUT_SECONDS = 10.0
MAX_MONGO_DOC_BYTES = 14 * 1024 * 1024


def _sse(payload: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def _progress(message: str, icon: str = "⟳", detail: str = "") -> str:
    return _sse({
        "type": "progress",
        "icon": icon,
        "message": message,
        "detail": detail,
    })


def _done(dataset_id: str, rows: int, columns: list, suggestions: list) -> str:
    return _sse({
        "type": "done",
        "dataset_id": dataset_id,
        "rows": rows,
        "columns": columns,
        "suggested_questions": suggestions,
        "message": "Dataset uploaded successfully",
    })


def _error(message: str) -> str:
    return _sse({"type": "error", "message": message})


async def upload_dataset_stream(
    filename: str,
    contents: bytes,
    user_id: str = "",
) -> AsyncGenerator[str, None]:
    """
    Async generator that runs the full upload pipeline and
    yields SSE-formatted strings at each step.
    """
    request_id = str(uuid.uuid4())[:8]
    t0 = time.perf_counter()

    def elapsed():
        return f"{time.perf_counter() - t0:.2f}s"

    logger.info(f"[{request_id}] Stream upload started: {filename}")

    # ── Step 1: Validate ──────────────────────────────────────────────────────
    yield _progress("Validating your file...", "📋")
    await asyncio.sleep(0)  # yield control to event loop

    extension = filename.rsplit(".", 1)[-1].lower()
    if extension not in ("csv", "xlsx"):
        yield _error("Only CSV or Excel files are supported.")
        return

    # ── Step 2: Parse file ────────────────────────────────────────────────────
    yield _progress("Reading and parsing your file...", "📂")
    await asyncio.sleep(0)

    try:
        if extension == "csv":
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))
    except Exception as e:
        logger.error(f"[{request_id}] Parse failed: {e}")
        yield _error(f"Could not parse file: {str(e)}")
        return

    df.columns = df.columns.str.strip()
    row_count = len(df)
    col_count = len(df.columns)

    logger.info(f"[{request_id}] Parsed: {row_count} rows × {col_count} cols ({elapsed()})")
    yield _progress(
        "File parsed successfully",
        "✓",
        f"{row_count:,} rows · {col_count} columns"
    )
    await asyncio.sleep(0.1)

    # ── Step 3: Schema analysis ───────────────────────────────────────────────
    yield _progress("Detecting columns and data types...", "🔍")
    await asyncio.sleep(0)

    dataset_id = str(uuid.uuid4())

    schema = [
        {"column_name": col, "dtype": str(df[col].dtype)}
        for col in df.columns
    ]

    try:
        detected = analyze_schema(df)
        schema_context = build_schema_context(df)
    except Exception as e:
        logger.error(f"[{request_id}] Schema analysis failed: {e}")
        yield _error(f"Schema analysis failed: {str(e)}")
        return

    metrics_count = len(detected.get("metrics", []))
    dims_count = len(detected.get("dimensions", []))

    yield _progress(
        "Schema detected",
        "✓",
        f"{metrics_count} metrics · {dims_count} dimensions"
    )
    await asyncio.sleep(0.1)

    # ── Step 4: LLM suggestions ───────────────────────────────────────────────
    yield _progress("Generating suggested questions with AI...", "🧠")
    await asyncio.sleep(0)

    try:
        provider = get_llm_provider()
        suggestions = await asyncio.wait_for(
            generate_question_suggestions(provider, schema_context),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        logger.info(f"[{request_id}] Got {len(suggestions)} suggestions ({elapsed()})")
        yield _progress(
            "AI suggestions ready",
            "✓",
            f"{len(suggestions)} questions generated"
        )
    except asyncio.TimeoutError:
        logger.warning(f"[{request_id}] LLM timed out")
        suggestions = []
        yield _progress("Skipped AI suggestions (timeout)", "⚠️")
    except Exception as e:
        logger.error(f"[{request_id}] LLM failed: {e}")
        suggestions = []
        yield _progress("Skipped AI suggestions", "⚠️")

    await asyncio.sleep(0.1)

    # ── Step 5: Save to MongoDB ───────────────────────────────────────────────
    yield _progress("Saving your dataset to database...", "💾")
    await asyncio.sleep(0)

    dataset_doc = {
        "dataset_id": dataset_id,
        "original_filename": filename,
        "columns": schema,
        "row_count": row_count,
        "data": df.to_dict(orient="records"),
        "uploaded_at": datetime.utcnow(),
        "user_id": user_id,
    }

    # Guard MongoDB 16MB limit
    try:
        import json as _json
        doc_size = len(_json.dumps(dataset_doc, default=str).encode("utf-8"))
        logger.debug(f"[{request_id}] Doc size: {doc_size / 1024:.1f} KB")
        if doc_size > MAX_MONGO_DOC_BYTES:
            yield _error(
                f"Dataset is too large ({doc_size / 1024 / 1024:.1f} MB). "
                "Please upload a smaller file or reduce rows."
            )
            return
    except Exception:
        pass

    try:
        await asyncio.wait_for(
            db.datasets.insert_one(dataset_doc),
            timeout=DB_TIMEOUT_SECONDS,
        )
        logger.info(f"[{request_id}] MongoDB insert OK ({elapsed()})")
        yield _progress("Dataset saved successfully", "✓")
    except asyncio.TimeoutError:
        yield _error("Database timeout — please try again.")
        return
    except Exception as e:
        logger.error(f"[{request_id}] MongoDB insert failed: {e}")
        yield _error(f"Failed to save dataset: {str(e)}")
        return

    await asyncio.sleep(0.1)

    # ── Done ──────────────────────────────────────────────────────────────────
    logger.info(f"[{request_id}] Stream upload complete in {elapsed()}")
    yield _done(dataset_id, row_count, schema, suggestions)