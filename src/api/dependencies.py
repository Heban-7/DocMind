"""FastAPI dependencies for DocMind: token verification and the caller's identity.

``get_principal`` is the **only** place that knows how tokens are decoded. To
move from local JWT to another identity provider, swap the implementation
here; routers stay unchanged.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer

from src.api.auth_utils import decode_access_token
from src.db.repos import Principal

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired authentication token.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _principal_from_token(token: str | None) -> Principal:
    if not token:
        raise _UNAUTHORIZED
    try:
        user_id, tenant_id = decode_access_token(token)
        return Principal(user_id=user_id, tenant_id=tenant_id)
    except (jwt.InvalidTokenError, ValueError):
        raise _UNAUTHORIZED from None


async def get_principal(token: str | None = Depends(_oauth2_scheme)) -> Principal:
    """Decode the Bearer token into the calling user and their tenant.

    Raises ``401 Unauthorized`` when the token is missing, expired, or invalid.
    """
    return _principal_from_token(token)


async def get_principal_header_or_query(
    header_token: str | None = Depends(_oauth2_scheme),
    token: str | None = Query(default=None, description="Bearer token, for <iframe> PDF views"),
) -> Principal:
    """Like ``get_principal`` but also accepts ``?token=``.

    Only for endpoints a browser loads directly (the PDF viewer), where no
    Authorization header can be attached. A token is always required.
    """
    return _principal_from_token(header_token or token)
