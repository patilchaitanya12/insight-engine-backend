from pydantic import BaseModel
import os
import pandas as pd
from fastapi import APIRouter, HTTPException

from app.core.database import db
from app.services.llm.factory import get_llm_provider
from app.utils.code_executor import CodeExecutor

class QueryRequest(BaseModel):
    dataset_id: str
    question: str


router = APIRouter()


@router.post("/")
async def run_query(request: QueryRequest):

    #Fetch dataset metadata
    dataset = await db.datasets.find_one({"dataset_id": request.dataset_id})

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    file_path = dataset["stored_path"]

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Dataset file missing")

    #Load CSV
    df = pd.read_csv(file_path)

    #Build LLM prompt
    columns_info = "\n".join(
        [f"- {col['column_name']} ({col['dtype']})" for col in dataset["columns"]]
    )

    prompt = f"""
Dataset columns:
{columns_info}

Question:
{request.question}
"""

    #Call LLM
    provider = get_llm_provider()
    llm_output = await provider.generate_structured(prompt)
    print("LLM Output:", llm_output)

    #Execute safely
    try:
        execution_result = CodeExecutor.execute(
            llm_output["analysis_code"],
            df
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    #Return final structured response
    return {
        "table": execution_result,
        "chart": {
            "chart_type": llm_output["chart_type"],
            "x_column": llm_output["x_column"],
            "y_column": llm_output["y_column"],
        },
        "insights": llm_output["insights"]
    }