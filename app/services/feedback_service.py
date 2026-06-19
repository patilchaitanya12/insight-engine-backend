import uuid
import logging
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId

from app.core.database import db

logger = logging.getLogger(__name__)


async def submit_feedback_service(
    user_id: str,
    query_history_id: str,
    dataset_id: str,
    question: str,
    rating: str,
    comment: str | None,
) -> dict:
    """
    Stores feedback linked back to the original query_history document.

    Verifies the query_history_id is a valid ObjectId and belongs to this
    user before accepting feedback — prevents users from submitting
    feedback against queries they don't own.
    """

    try:
        history_oid = ObjectId(query_history_id)
    except (InvalidId, TypeError):
        raise ValueError("Invalid query_history_id")

    # Verify ownership — the query this feedback references must belong
    # to the user submitting it.
    history_doc = await db.query_history.find_one({
        "_id": history_oid,
        "user_id": user_id,
    })

    if not history_doc:
        logger.warning(
            f"Feedback rejected: query_history {query_history_id} "
            f"not found or not owned by user {user_id}"
        )
        raise ValueError("Query not found")

    feedback_id = str(uuid.uuid4())

    feedback_doc = {
        "feedback_id": feedback_id,
        "user_id": user_id,
        "query_history_id": history_oid,
        "dataset_id": dataset_id,
        "question": question,
        "rating": rating,
        "comment": comment,
        "timestamp": datetime.utcnow(),
    }

    await db.feedback.insert_one(feedback_doc)

    logger.info(
        f"Feedback saved: user={user_id} rating={rating} "
        f"query_history_id={query_history_id}"
    )

    return {
        "feedback_id": feedback_id,
        "status": "saved",
    }
