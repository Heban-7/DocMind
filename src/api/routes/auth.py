"""Authentication routes: register, login and profile, by email.

Registering creates a new tenant with the user as its owner, so every account
starts with its own private document space.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth_utils import create_access_token, hash_password, verify_password
from src.api.dependencies import get_principal
from src.api.schemas import TokenResponse, UserLogin, UserProfile, UserRegister
from src.db import repos
from src.db.repos import Principal

logger = logging.getLogger("docmind.auth")

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verifying against a real hash for unknown emails keeps login timing the same
# whether or not the account exists.
_DUMMY_HASH = hash_password("docmind-timing-equaliser")


@auth_router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister) -> UserProfile:
    """Register a new user (and their tenant) with a unique email and password."""
    clean_email = payload.email.strip().lower()
    try:
        principal = repos.create_tenant_with_owner(clean_email, hash_password(payload.password))
    except repos.EmailTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{clean_email}' already exists.",
        ) from None
    logger.info("User registered: id=%s tenant=%s", principal.user_id, principal.tenant_id)
    return UserProfile(id=principal.user_id, email=clean_email)


@auth_router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin) -> TokenResponse:
    """Authenticate with email and password, returning a JWT access token."""
    user = repos.get_user_by_email(payload.email)
    valid = verify_password(payload.password, user["hashed_password"] if user else _DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    logger.info("User logged in: id=%s", user["id"])
    return TokenResponse(access_token=create_access_token(user["id"], user["tenant_id"]))


@auth_router.get("/me", response_model=UserProfile)
def me(principal: Principal = Depends(get_principal)) -> UserProfile:
    """Return the profile for the currently authenticated user."""
    user = repos.get_user(principal.user_id)
    if not user or user["tenant_id"] != principal.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return UserProfile(id=user["id"], email=user["email"])
