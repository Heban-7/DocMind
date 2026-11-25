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


def create_access_token(user_id: str, tenant_id: str) -> str:
    """Create a signed JWT: ``sub`` = user id, ``tid`` = tenant id, with expiry."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tid": tenant_id,
        "iat": now,
        "exp": now + timedelta(hours=_expiry_hours()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> tuple[str, str]:
    """Decode a JWT and return ``(user_id, tenant_id)``.

    Raises ``jwt.InvalidTokenError`` on any validation failure, including
    tokens issued before tenants existed (no ``tid`` claim).
    """
    payload = jwt.decode(
        token,
        jwt_secret(),
        algorithms=[_ALGORITHM],
        options={"require": ["exp", "sub", "tid"]},
    )
    if payload.get("scope"):
        # a file link opens one document; it is not a sign-in
        raise jwt.InvalidTokenError("file link used as an access token")
    user_id = payload.get("sub")
    tenant_id = payload.get("tid")
    if not user_id or not tenant_id:
        raise jwt.InvalidTokenError("Token missing 'sub' or 'tid' claim")
    return str(user_id), str(tenant_id)


FILE_LINK_SECONDS = 600


def create_file_token(user_id: str, tenant_id: str, document_id: str, *, seconds: int = FILE_LINK_SECONDS) -> str:
    """A short-lived token that opens one document's files, for links a browser loads directly.

    The sign-in token never goes into a URL (URLs end up in browser history,
    server logs and Referer headers); this one is valid for ten minutes and
    for one document only.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id, "tid": tenant_id, "doc": document_id, "scope": "file",
        "iat": now, "exp": now + timedelta(seconds=seconds),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=_ALGORITHM)


def decode_file_token(token: str, document_id: str) -> tuple[str, str]:
    """``(user_id, tenant_id)`` of a file link for ``document_id``; InvalidTokenError otherwise."""
    payload = jwt.decode(
        token, jwt_secret(), algorithms=[_ALGORITHM], options={"require": ["exp", "sub", "tid", "doc", "scope"]}
    )
    if payload.get("scope") != "file" or str(payload.get("doc")) != str(document_id):
        raise jwt.InvalidTokenError("file link for another document")
    return str(payload["sub"]), str(payload["tid"])
