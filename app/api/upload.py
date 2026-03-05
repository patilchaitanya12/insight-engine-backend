import uuid
import pandas as pd
from io import BytesIO
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.core.database import db

router = APIRouter()


@router.post("/")
async def upload_dataset(file: UploadFile = File(...)):

    filename = file.filename

    if not filename:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must have a filename"
        )

    if not filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(
            status_code=400,
            detail="Only CSV or Excel files supported"
        )

    extension = filename.rsplit(".", 1)[-1].lower()

    contents = await file.read()

    try:
        if extension == "csv":
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid dataset file")

    df.columns = df.columns.str.strip()

    dataset_id = str(uuid.uuid4())

    schema = [
        {"column_name": col, "dtype": str(df[col].dtype)}
        for col in df.columns
    ]

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
        "message": "Dataset uploaded successfully"
    }
