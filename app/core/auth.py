"""
Clerk JWT verification for FastAPI.

Verifies the Bearer token sent by the frontend (via Clerk's getToken())
against Clerk's public JWKS endpoint, and extracts the user_id (the
JWT "sub" claim).

Usage in a route:

    from app.core.auth import get_current_user_id

    @router.post("/")
    async def my_route(user_id: str = Depends(get_current_user_id)):
        ...
"""

import logging
import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

# PyJWKClient caches keys internally and auto-refreshes when a kid is unknown
_jwks_client = PyJWKClient(settings.CLERK_JWKS_URL)


async def get_current_user_id(authorization: str | None = Header(None)) -> str:
    """
    Extracts and verifies the Clerk JWT from the Authorization header.
    Returns the Clerk user_id (the "sub" claim) on success.
    Raises 401 if the token is missing, malformed, or invalid.
    """

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk tokens don't always set aud
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing user ID")

    return user_id


async def get_optional_user_id(authorization: str | None = Header(None)) -> str | None:
    """
    Same as get_current_user_id but returns None instead of raising
    if no token is provided. Useful for routes that work for both
    signed-in and anonymous users (e.g. sample datasets).
    """
    if not authorization:
        return None
    try:
        return await get_current_user_id(authorization)
    except HTTPException:
        return None