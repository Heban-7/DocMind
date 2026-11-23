"""Who may see which document and which chat thread.

Interim access control until the Postgres migration (V2 milestone M3), where
every row carries a tenant id enforced by row-level security. Until then:

* A document is visible only to the users who uploaded it.
* Documents ingested before ownership was recorded ("legacy" documents) are
  hidden from everyone, unless ``DOCMIND_LEGACY_SHARED_DOCS=1`` is set for a
  local demo of the public corpus.
* A chat thread belongs to the first user who writes to it; nobody else can
  read it or post to it.

Ownership lives in the same SQLite file as the users table
(``CHECKPOINTS_DB_PATH``).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src import config


class AccessDeniedError(LookupError):
    """The resource does not exist for this user (deliberately not 403)."""


def _db_path() -> Path:
    # Read at call time so tests and deployments can point it elsewhere.
    return config.CHECKPOINTS_DB_PATH


_SCHEMA = """
CREATE TABLE IF NOT EXISTS document_owners (
    doc_id     TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (doc_id, user_id)
);
CREATE TABLE IF NOT EXISTS thread_owners (
    thread_id  TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        conn.executescript(_SCHEMA)
        _migrate_legacy_thread_owners(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate_legacy_thread_owners(conn: sqlite3.Connection) -> None:
    """Carry over owners recorded by the old ``thread_documents`` table."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='thread_documents'"
    ).fetchone()
    if exists:
        conn.execute(
            "INSERT OR IGNORE INTO thread_owners (thread_id, user_id) "
            "SELECT thread_id, user_id FROM thread_documents WHERE user_id != ''"
        )


def legacy_documents_shared() -> bool:
    return os.getenv("DOCMIND_LEGACY_SHARED_DOCS", "").lower() in {"1", "true", "yes"}


# --- Documents ---------------------------------------------------------------


def record_document_owner(doc_id: str, user_id: str) -> None:
    """Grant ``user_id`` access to ``doc_id`` (idempotent)."""
    if not doc_id or not user_id:
        raise ValueError("doc_id and user_id are required")
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO document_owners (doc_id, user_id) VALUES (?, ?)",
            (doc_id, user_id),
        )


def document_owners(doc_id: str) -> set[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT user_id FROM document_owners WHERE doc_id = ?", (doc_id,)
        ).fetchall()
    return {r[0] for r in rows}


def can_access_document(doc_id: str, user_id: str) -> bool:
    """True when the user owns the document (or legacy sharing is enabled)."""
    if not doc_id or not user_id:
        return False
    owners = document_owners(doc_id)
    if owners:
        return user_id in owners
    return legacy_documents_shared()


def require_document_access(doc_id: str, user_id: str) -> None:
    if not can_access_document(doc_id, user_id):
        raise AccessDeniedError(f"Document {doc_id!r} not found.")


# --- Chat threads ------------------------------------------------------------


def thread_owner(thread_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM thread_owners WHERE thread_id = ?", (thread_id,)
        ).fetchone()
    return row[0] if row else None


def claim_thread(thread_id: str, user_id: str) -> None:
    """Make ``user_id`` the owner of a new thread, or confirm they already are.

    Raises AccessDeniedError when the thread belongs to someone else. Ownership
    is never transferred.
    """
    if not thread_id or not user_id:
        raise ValueError("thread_id and user_id are required")
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO thread_owners (thread_id, user_id) VALUES (?, ?)",
            (thread_id, user_id),
        )
        row = conn.execute(
            "SELECT user_id FROM thread_owners WHERE thread_id = ?", (thread_id,)
        ).fetchone()
    if not row or row[0] != user_id:
        raise AccessDeniedError(f"Thread {thread_id!r} not found.")


def require_thread_access(thread_id: str, user_id: str) -> None:
    """Fail closed: unknown threads and other users' threads are both denied."""
    if not user_id or thread_owner(thread_id) != user_id:
        raise AccessDeniedError(f"Thread {thread_id!r} not found.")


def threads_owned_by(user_id: str) -> set[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT thread_id FROM thread_owners WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {r[0] for r in rows}
