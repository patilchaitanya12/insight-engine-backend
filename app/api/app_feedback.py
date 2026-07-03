from typing import Literal
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends

from app.services.app_feedback_service import submit_app_feedback_service
from app.core.auth import get_current_user_id


class AppFeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


router = APIRouter()


@router.post("/")
async def submit_app_feedback(
    request: AppFeedbackRequest,
    user_id: str = Depends(get_current_user_id),
):
    try:
        result = await submit_app_feedback_service(
            user_id=user_id,
            rating=request.rating,
            comment=request.comment,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit feedback: {str(e)}"
        )