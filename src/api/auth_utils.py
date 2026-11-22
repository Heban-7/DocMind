"""Password hashing and JWT token utilities for DocMind authentication."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Importing config loads the project's .env file. It must happen before any
# secret is read, otherwise a JWT_SECRET_KEY kept in .env is silently ignored.
import src.config  # noqa: F401  (side effect: loads .env)

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
_ALGORITHM = "HS256"
_MIN_SECRET_LENGTH = 32
# Values that have appeared in this repo or its docs. A token signed with any of
# them could be forged by anyone who reads the code, so they are refused.
_KNOWN_PUBLIC_SECRETS = frozenset(
    {
        "docmind-dev-secret-change-me-in-production",
        "production_jwt_secret_key_change_in_vault",
        "generate_with_openssl_rand_hex_32",
    }
)


class InsecureSecretError(RuntimeError):
    """Raised when JWT_SECRET_KEY is missing, too short or publicly known."""


def jwt_secret() -> str:
    """Return the signing secret, refusing missing or weak values.

    There is deliberately no fallback: a default secret in source code lets
    anyone mint a valid token for any user id.
    """
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not secret or secret in _KNOWN_PUBLIC_SECRETS or len(secret) < _MIN_SECRET_LENGTH:
        raise InsecureSecretError(
            "JWT_SECRET_KEY is missing, too short or a known public value. "
            f"Set a random value of at least {_MIN_SECRET_LENGTH} characters, e.g. "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return secret


def _expiry_hours() -> int:
    return int(os.getenv("JWT_EXPIRY_HOURS", "24"))


def create_access_token(user_id: str) -> str:
    """Create a signed JWT with ``sub=user_id`` and an expiry timestamp."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=_expiry_hours()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Decode a JWT and return the ``user_id`` (``sub`` claim).

    Raises ``jwt.InvalidTokenError`` on any validation failure.
    """
    payload = jwt.decode(
        token,
        jwt_secret(),
        algorithms=[_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise jwt.InvalidTokenError("Token missing 'sub' claim")
    return user_id
