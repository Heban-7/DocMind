"""Authentication routes: register, login, and profile using Email."""

from __future__ import annotations

import logging
import sqlite3
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth_utils import create_access_token, hash_password, verify_password
from src.api.dependencies import get_current_user_id
from src.api.schemas import TokenResponse, UserLogin, UserProfile, UserRegister
from src.config import CHECKPOINTS_DB_PATH

logger = logging.getLogger("docmind.auth")

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

_USERS_DB = CHECKPOINTS_DB_PATH


def _init_users_table() -> None:
    """Create the ``users`` table if it does not exist, with email column."""
    _USERS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_USERS_DB))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id           TEXT PRIMARY KEY,
            email        TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Check if table had legacy username column and migrate if needed
    try:
        conn.execute("SELECT email FROM users LIMIT 1")
    except sqlite3.OperationalError:
        try:
            conn.execute("ALTER TABLE users RENAME COLUMN username TO email")
        except Exception:
            pass
    conn.commit()
    conn.close()


def _get_user_by_email(email: str) -> dict | None:
    conn = sqlite3.connect(str(_USERS_DB))
    cursor = conn.execute(
        "SELECT id, email, hashed_password FROM users WHERE LOWER(email) = LOWER(?)",
        (email.strip(),),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "email": row[1], "hashed_password": row[2]}
    return None


def _get_user_by_id(user_id: str) -> dict | None:
    conn = sqlite3.connect(str(_USERS_DB))
    cursor = conn.execute(
        "SELECT id, email FROM users WHERE id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "email": row[1]}
    return None


def _create_user(email: str, hashed_password: str) -> str:
    user_id = uuid4().hex
    conn = sqlite3.connect(str(_USERS_DB))
    conn.execute(
        "INSERT INTO users (id, email, hashed_password) VALUES (?, ?, ?)",
        (user_id, email.strip().lower(), hashed_password),
    )
    conn.commit()
    conn.close()
    return user_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@auth_router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister) -> UserProfile:
    """Register a new user with a unique email and password."""
    _init_users_table()
    clean_email = payload.email.strip().lower()

    existing = _get_user_by_email(clean_email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{clean_email}' already exists.",
        )

    hashed = hash_password(payload.password)
    user_id = _create_user(clean_email, hashed)
    logger.info("User registered: email=%s id=%s", clean_email, user_id)
    return UserProfile(id=user_id, email=clean_email)


@auth_router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin) -> TokenResponse:
    """Authenticate with email and password, returning a JWT access token."""
    _init_users_table()
    clean_email = payload.email.strip().lower()

    user = _get_user_by_email(clean_email)
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token(user["id"])
    logger.info("User logged in: email=%s", clean_email)
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserProfile)
def me(user_id: str = Depends(get_current_user_id)) -> UserProfile:
    """Return the profile for the currently authenticated user."""
    user = _get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return UserProfile(id=user["id"], email=user["email"])
