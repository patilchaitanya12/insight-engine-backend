from typing import Literal
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends

from app.services.feedback_service import submit_feedback_service
from app.core.auth import get_current_user_id


class FeedbackRequest(BaseModel):
    query_history_id: str
    dataset_id: str
    question: str
    rating: Literal["up", "down"]
    comment: str | None = None


router = APIRouter()


@router.post("/")
async def submit_feedback(
    request: FeedbackRequest,
    user_id: str = Depends(get_current_user_id),
):
    try:
        result = await submit_feedback_service(
            user_id=user_id,
            query_history_id=request.query_history_id,
            dataset_id=request.dataset_id,
            question=request.question,
            rating=request.rating,
            comment=request.comment,
        )
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit feedback: {str(e)}"
        )
