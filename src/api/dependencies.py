"""FastAPI dependencies for DocMind — token verification & user resolution.

The single ``get_current_user_id`` dependency is the **only** place that knows
how tokens are decoded.  To migrate from local JWT to Clerk (or any other
provider), swap the implementation here — all routers stay unchanged.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from src.api.auth_utils import decode_access_token

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user_id(
    token: str = Depends(_oauth2_scheme),
) -> str:
    """Decode the Bearer token and return the authenticated ``user_id``.

    Raises ``401 Unauthorized`` when the token is missing, expired, or invalid.
    """
    try:
        return decode_access_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
