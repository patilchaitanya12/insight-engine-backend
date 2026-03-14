import uuid
import pandas as pd
from io import BytesIO
from datetime import datetime

from app.core.database import db
from app.services.schema_analyzer import analyze_schema
from app.services.question_suggester import generate_question_suggestions
from app.utils.schema_builder import build_schema_context
from app.services.llm.factory import get_llm_provider


async def upload_dataset_service(file):

    filename = file.filename

    if not filename:
        return {"error": "Uploaded file must have a filename"}

    if not filename.lower().endswith((".csv", ".xlsx")):
        return {"error": "Only CSV or Excel files supported"}

    extension = filename.rsplit(".", 1)[-1].lower()

    contents = await file.read()

    try:

        if extension == "csv":
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))

    except Exception:
        return {"error": "Invalid dataset file"}

    df.columns = df.columns.str.strip()

    dataset_id = str(uuid.uuid4())

    schema = [
        {"column_name": col, "dtype": str(df[col].dtype)}
        for col in df.columns
    ]

    schema_context = build_schema_context(df)

    provider = get_llm_provider()

    suggestions = await generate_question_suggestions(
        provider,
        schema_context
    )

    dataset_doc = {
        "dataset_id": dataset_id,
        "original_filename": filename,
        "columns": schema,
        "row_count": len(df),
        "data": df.to_dict(orient="records"),
        "uploaded_at": datetime.utcnow()
    }

    await db.datasets.insert_one(dataset_doc)

    return {
        "dataset_id": dataset_id,
        "rows": len(df),
        "columns": schema,
        "suggested_questions": suggestions,
        "message": "Dataset uploaded successfully"
    }
