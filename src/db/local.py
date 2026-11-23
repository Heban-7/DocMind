"""A fixed local account for the command-line tools and the benchmark.

The CLI has no login, so it works inside one tenant of its own. The account
gets a random password nobody knows, so it cannot be used to sign in to the
API.
"""

from __future__ import annotations

import secrets

from src.db import repos
from src.db.repos import Principal

LOCAL_EMAIL = "local-cli@docmind.invalid"


def local_principal(email: str = LOCAL_EMAIL) -> Principal:
    user = repos.get_user_by_email(email)
    if user is not None:
        return Principal(user_id=user["id"], tenant_id=user["tenant_id"])
    from src.api.auth_utils import hash_password

    try:
        return repos.create_tenant_with_owner(email, hash_password(secrets.token_urlsafe(32)), tenant_name=email)
    except repos.EmailTakenError:  # created concurrently
        user = repos.get_user_by_email(email)
        return Principal(user_id=user["id"], tenant_id=user["tenant_id"])
