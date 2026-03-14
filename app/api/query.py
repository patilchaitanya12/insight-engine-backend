
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.services.query_service import run_query_service


class QueryRequest(BaseModel):
    dataset_id: str
    question: str


router = APIRouter()


@router.post("/")
async def run_query(request: QueryRequest):

    try:

        result = await run_query_service(
            request.dataset_id,
            request.question
        )

        return result

    except ValueError as e:

        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Query execution failed: {str(e)}"
        )
