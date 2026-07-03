import uuid
import logging
from datetime import datetime

from app.core.database import db

logger = logging.getLogger(__name__)


async def submit_app_feedback_service(
    user_id: str,
    rating: int,
    comment: str | None,
) -> dict:
    """
    Stores overall app feedback in the `app_feedback` collection.
    Separate from per-query feedback (insight/chart thumbs) stored
    in the `feedback` collection — this is for the whole app experience.
    """
    feedback_id = str(uuid.uuid4())

    doc = {
        "feedback_id": feedback_id,
        "user_id": user_id,
        "rating": rating,
        "comment": comment,
        "timestamp": datetime.utcnow(),
    }

    await db.app_feedback.insert_one(doc)

    logger.info(
        f"App feedback saved: user={user_id} rating={rating}/5"
    )

    return {
        "feedback_id": feedback_id,
        "status": "saved",
    }