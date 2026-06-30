"""
Keeps a `users` collection in sync with Clerk.

Every time a request comes in with a valid JWT, we upsert a lightweight
record: user_id, email, name, joined_at (set once), last_seen_at (updated
every call). Other collections (feedback, query_history, datasets) only
ever store user_id — to get email/name, join against this collection.
"""

import logging
from datetime import datetime

from app.core.database import db

logger = logging.getLogger(__name__)


async def upsert_user(user_id: str, email: str | None, name: str | None) -> None:
    now = datetime.utcnow()

    update_doc = {
        "$set": {
            "user_id": user_id,
            "last_seen_at": now,
        },
        "$setOnInsert": {
            "joined_at": now,
        },
    }

    # Only overwrite email/name if we actually have a value — avoids
    # clobbering existing data with None on tokens that lack the claim.
    if email:
        update_doc["$set"]["email"] = email
    if name:
        update_doc["$set"]["name"] = name

    try:
        await db.users.update_one(
            {"user_id": user_id},
            update_doc,
            upsert=True,
        )
    except Exception as e:
        # Never let user-sync failures break the actual request
        logger.warning(f"Failed to upsert user {user_id}: {e}")