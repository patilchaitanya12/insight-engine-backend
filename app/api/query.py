from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends

from app.services.query_service import run_query_service
from app.core.auth import get_current_user_id
from app.core.database import db


class QueryRequest(BaseModel):
    dataset_id: str
    question: str


router = APIRouter()


@router.post("/")
async def run_query(
    request: QueryRequest,
    user_id: str = Depends(get_current_user_id),
):

    try:

        result = await run_query_service(
            request.dataset_id,
            request.question,
            user_id=user_id,
        )

        return result

    except ValueError as e:

        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Query execution failed: {str(e)}"
        )


@router.get("/history")
async def get_query_history(
    dataset_id: str | None = None,
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """
    Returns this user's past queries, optionally filtered by dataset_id.
    Used by the frontend to show "Recent queries" on return visits.
    """
    query_filter = {"user_id": user_id}
    if dataset_id:
        query_filter["dataset_id"] = dataset_id

    cursor = (
        db.query_history
        .find(query_filter, {"_id": 0})
        .sort("timestamp", -1)
        .limit(limit)
    )

    history = await cursor.to_list(length=limit)

    return {"history": history}