import uuid
import asyncio
import logging
import time
import sys
from io import BytesIO
from datetime import datetime

import pandas as pd

from app.core.database import db
from app.services.schema_analyzer import analyze_schema
from app.services.question_suggester import generate_question_suggestions
from app.utils.schema_builder import build_schema_context
from app.services.llm.factory import get_llm_provider

# ── Logger setup ────────────────────────────────────────────────────────────
logger = logging.getLogger("upload_service")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [upload_service] %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ── Constants ────────────────────────────────────────────────────────────────
LLM_TIMEOUT_SECONDS   = 15.0   # max wait for question suggestions
DB_TIMEOUT_SECONDS    = 10.0   # max wait for MongoDB insert
MAX_FILE_SIZE_BYTES   = 10 * 1024 * 1024   # 10 MB hard limit
MAX_MONGO_DOC_BYTES   = 14 * 1024 * 1024   # ~14 MB (Mongo limit is 16 MB)


async def upload_dataset_service(file, user_id: str):
    request_id = str(uuid.uuid4())[:8]   # short ID to correlate log lines
    t0 = time.perf_counter()

    def elapsed():
        return f"{time.perf_counter() - t0:.2f}s"

    logger.info(f"[{request_id}] ── Upload started (user={user_id}) ──────────────────────────")

    # ── 1. Validate filename ─────────────────────────────────────────────────
    filename = file.filename
    logger.debug(f"[{request_id}] filename={filename!r}")

    if not filename:
        logger.warning(f"[{request_id}] Rejected: no filename")
        return {"error": "Uploaded file must have a filename"}

    if not filename.lower().endswith((".csv", ".xlsx")):
        logger.warning(f"[{request_id}] Rejected: unsupported extension ({filename})")
        return {"error": "Only CSV or Excel files supported"}

    extension = filename.rsplit(".", 1)[-1].lower()

    # ── 2. Read raw bytes ────────────────────────────────────────────────────
    logger.debug(f"[{request_id}] Reading file bytes...")
    try:
        contents = await file.read()
    except Exception as e:
        logger.error(f"[{request_id}] Failed to read file bytes: {e}", exc_info=True)
        return {"error": f"Could not read uploaded file: {str(e)}"}

    file_size = len(contents)
    logger.info(f"[{request_id}] File read: {file_size} bytes ({elapsed()})")

    if file_size == 0:
        logger.warning(f"[{request_id}] Rejected: empty file")
        return {"error": "Uploaded file is empty"}

    if file_size > MAX_FILE_SIZE_BYTES:
        logger.warning(f"[{request_id}] Rejected: file too large ({file_size} bytes)")
        return {"error": f"File exceeds 10 MB limit ({file_size / 1024 / 1024:.1f} MB)"}

    # ── 3. Parse into DataFrame ──────────────────────────────────────────────
    logger.debug(f"[{request_id}] Parsing {extension.upper()} file...")
    try:
        if extension == "csv":
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))
    except Exception as e:
        logger.error(f"[{request_id}] Parse failed: {e}", exc_info=True)
        return {"error": f"Could not parse file: {str(e)}"}

    df.columns = df.columns.str.strip()
    logger.info(
        f"[{request_id}] Parsed OK: {len(df)} rows × {len(df.columns)} columns "
        f"({elapsed()})"
    )
    logger.debug(f"[{request_id}] Columns: {list(df.columns)}")

    # ── 4. Build schema ──────────────────────────────────────────────────────
    dataset_id = str(uuid.uuid4())
    logger.info(f"[{request_id}] dataset_id={dataset_id}")

    schema = [
        {"column_name": col, "dtype": str(df[col].dtype)}
        for col in df.columns
    ]

    try:
        schema_context = build_schema_context(df)
        logger.debug(f"[{request_id}] schema_context built ({elapsed()})")
    except Exception as e:
        logger.error(f"[{request_id}] build_schema_context failed: {e}", exc_info=True)
        return {"error": f"Schema analysis failed: {str(e)}"}

    # ── 5. LLM suggestions (with timeout) ────────────────────────────────────
    logger.debug(f"[{request_id}] Requesting LLM suggestions (timeout={LLM_TIMEOUT_SECONDS}s)...")
    try:
        provider = get_llm_provider()
        suggestions = await asyncio.wait_for(
            generate_question_suggestions(provider, schema_context),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        logger.info(f"[{request_id}] Got {len(suggestions)} suggestions ({elapsed()})")
    except asyncio.TimeoutError:
        logger.warning(
            f"[{request_id}] LLM suggestions timed out after {LLM_TIMEOUT_SECONDS}s — "
            f"continuing with empty suggestions"
        )
        suggestions = []
    except Exception as e:
        logger.error(f"[{request_id}] LLM suggestions failed: {e}", exc_info=True)
        suggestions = []   # non-fatal — don't block the upload

    # ── 6. Build MongoDB document ─────────────────────────────────────────────
    dataset_doc = {
        "dataset_id": dataset_id,
        "user_id": user_id,
        "original_filename": filename,
        "columns": schema,
        "row_count": len(df),
        "data": df.to_dict(orient="records"),
        "uploaded_at": datetime.utcnow(),
    }

    # Guard against hitting the 16 MB MongoDB document limit
    import json
    try:
        doc_size = len(json.dumps(dataset_doc, default=str).encode("utf-8"))
        logger.debug(f"[{request_id}] Estimated MongoDB doc size: {doc_size / 1024:.1f} KB")
        if doc_size > MAX_MONGO_DOC_BYTES:
            logger.error(
                f"[{request_id}] Document too large for MongoDB: {doc_size} bytes "
                f"(limit ~{MAX_MONGO_DOC_BYTES} bytes)"
            )
            return {
                "error": (
                    f"Dataset is too large to store ({doc_size / 1024 / 1024:.1f} MB). "
                    "Please upload a smaller file."
                )
            }
    except Exception as e:
        logger.warning(f"[{request_id}] Could not estimate doc size: {e}")

    # ── 7. Insert into MongoDB (with timeout) ─────────────────────────────────
    logger.debug(f"[{request_id}] Inserting into MongoDB (timeout={DB_TIMEOUT_SECONDS}s)...")
    try:
        await asyncio.wait_for(
            db.datasets.insert_one(dataset_doc),
            timeout=DB_TIMEOUT_SECONDS,
        )
        logger.info(f"[{request_id}] MongoDB insert OK ({elapsed()})")
    except asyncio.TimeoutError:
        logger.error(
            f"[{request_id}] MongoDB insert timed out after {DB_TIMEOUT_SECONDS}s"
        )
        return {"error": "Database timeout — please try again"}
    except Exception as e:
        logger.error(f"[{request_id}] MongoDB insert failed: {e}", exc_info=True)
        return {"error": f"Failed to save dataset: {str(e)}"}

    # ── 8. Success ────────────────────────────────────────────────────────────
    logger.info(
        f"[{request_id}] ── Upload complete in {elapsed()} ── "
        f"dataset_id={dataset_id}"
    )

    return {
        "dataset_id": dataset_id,
        "rows": len(df),
        "columns": schema,
        "suggested_questions": suggestions,
        "message": "Dataset uploaded successfully",
    }