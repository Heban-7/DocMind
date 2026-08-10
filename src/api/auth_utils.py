"""Password hashing and JWT token utilities for DocMind authentication."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# ---------------------------------------------------------------------------
# Password hashing (Argon2id via pwdlib)
# ---------------------------------------------------------------------------
_pw_hash = PasswordHash((Argon2Hasher(),))


def hash_password(raw: str) -> str:
    """Hash a raw password string using Argon2id."""
    return _pw_hash.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    """Verify a raw password against an Argon2id hash."""
    return _pw_hash.verify(raw, hashed)


# ---------------------------------------------------------------------------
# JWT token creation & decoding
# ---------------------------------------------------------------------------
_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "docmind-dev-secret-change-me-in-production",
)
_ALGORITHM = "HS256"
_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))


def create_access_token(user_id: str) -> str:
    """Create a signed JWT with ``sub=user_id`` and an expiry timestamp."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=_EXPIRY_HOURS),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Decode a JWT and return the ``user_id`` (``sub`` claim).

    Raises ``jwt.InvalidTokenError`` on any validation failure.
    """
    payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise jwt.InvalidTokenError("Token missing 'sub' claim")
    return user_id
