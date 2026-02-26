import os
import uuid
import pandas as pd
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.core.database import db

router = APIRouter()

DATASET_DIR = "datasets"


@router.post("/")
async def upload_dataset(file: UploadFile = File(...)):

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files supported")

    #Generate unique dataset id
    dataset_id = str(uuid.uuid4())

    #Save file to disk
    file_path = os.path.join(DATASET_DIR, f"{dataset_id}.csv")

    contents = await file.read()

    with open(file_path, "wb") as f:
        f.write(contents)

    #Load into pandas to extract schema
    try:
        df = pd.read_csv(file_path)
    except Exception:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail="Invalid CSV file")

    schema = [
        {"column_name": col, "dtype": str(df[col].dtype)}
        for col in df.columns
    ]

    #Store metadata in Mongo
    dataset_doc = {
        "dataset_id": dataset_id,
        "original_filename": file.filename,
        "stored_path": file_path,
        "columns": schema,
        "uploaded_at": datetime.utcnow(),
    }

    await db.datasets.insert_one(dataset_doc)

    return {
        "dataset_id": dataset_id,
        "columns": schema,
        "message": "Dataset uploaded successfully"
    }