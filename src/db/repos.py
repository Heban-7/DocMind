"""Tenants, users, documents, page ledgers and chat threads.

Users and tenants are read before a tenant is known (login), so they are the
only tables without row-level security. Everything else goes through
``tenant_tx``: a row of another tenant is simply not there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from src.db.pool import app_tx, tenant_tx
from src.stores.pg import as_uuid


class AccessDeniedError(LookupError):
    """The resource does not exist for this caller (deliberately not 403)."""


class EmailTakenError(ValueError):
    pass


@dataclass(frozen=True)
class Principal:
    """Who is calling: a user inside one tenant."""

    user_id: str
    tenant_id: str

    def __post_init__(self) -> None:
        if as_uuid(self.user_id) is None or as_uuid(self.tenant_id) is None:
            raise ValueError("Principal ids must be UUIDs")


# --- Users and tenants (no RLS) ------------------------------------------------


def create_tenant_with_owner(email: str, hashed_password: str, *, tenant_name: str = "") -> Principal:
    """Register a user in a new tenant of their own, as its owner."""
    clean = email.strip().lower()
    try:
        with app_tx() as conn:
            tenant = conn.execute(
                "INSERT INTO tenants (name) VALUES (%s) RETURNING id", (tenant_name or clean,)
            ).fetchone()
            user = conn.execute(
                "INSERT INTO users (tenant_id, email, hashed_password, role) VALUES (%s, %s, %s, 'owner') RETURNING id",
                (tenant["id"], clean, hashed_password),
            ).fetchone()
    except psycopg.errors.UniqueViolation as exc:
        raise EmailTakenError(clean) from exc
    return Principal(user_id=str(user["id"]), tenant_id=str(tenant["id"]))


def get_user_by_email(email: str) -> dict | None:
    with app_tx() as conn:
        row = conn.execute(
            "SELECT id, tenant_id, email, hashed_password FROM users WHERE email = %s", (email.strip().lower(),)
        ).fetchone()
    return _stringify(row)


def get_user(user_id: str) -> dict | None:
    uid = as_uuid(user_id)
    if uid is None:
        return None
    with app_tx() as conn:
        row = conn.execute("SELECT id, tenant_id, email FROM users WHERE id = %s", (uid,)).fetchone()
    return _stringify(row)


def _stringify(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in row.items()}


# --- Documents -------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentRow:
    id: str
    sha256: str
    file_name: str
    page_count: int
    status: str
    storage_key: str
    model_key: str | None
    pages_needing_review: int
    domain_hint: str
    stats: dict[str, Any]
    error: str | None
    created_at: datetime


_DOC_COLUMNS = (
    "id, sha256, file_name, page_count, status, storage_key, model_key, pages_needing_review,"
    " domain_hint, stats, error, created_at"
)


def _doc(row: dict | None) -> DocumentRow | None:
    if row is None:
        return None
    data = dict(row)
    data["id"] = str(data["id"])
    return DocumentRow(**data)


def new_document_id() -> str:
    return str(uuid4())


def create_document(
    principal: Principal,
    *,
    document_id: str,
    sha256: str,
    file_name: str,
    storage_key: str,
) -> DocumentRow:
    with tenant_tx(principal.tenant_id) as conn:
        row = conn.execute(
            "INSERT INTO documents (id, sha256, file_name, storage_key, status, created_by)"
            f" VALUES (%s, %s, %s, %s, 'processing', %s) RETURNING {_DOC_COLUMNS}",
            (document_id, sha256, file_name, storage_key, principal.user_id),
        ).fetchone()
    return _doc(row)


def get_document(tenant_id: str, document_id: str) -> DocumentRow | None:
    did = as_uuid(document_id)
    if did is None:
        return None
    with tenant_tx(tenant_id) as conn:
        row = conn.execute(f"SELECT {_DOC_COLUMNS} FROM documents WHERE id = %s", (did,)).fetchone()
    return _doc(row)


def require_document(tenant_id: str, document_id: str) -> DocumentRow:
    doc = get_document(tenant_id, document_id)
    if doc is None:
        raise AccessDeniedError(f"Document {document_id!r} not found.")
    return doc


def find_document_by_sha(tenant_id: str, sha256: str) -> DocumentRow | None:
    with tenant_tx(tenant_id) as conn:
        row = conn.execute(f"SELECT {_DOC_COLUMNS} FROM documents WHERE sha256 = %s", (sha256,)).fetchone()
    return _doc(row)


def list_documents(tenant_id: str, *, ready_only: bool = False) -> list[DocumentRow]:
    sql = f"SELECT {_DOC_COLUMNS} FROM documents"
    if ready_only:
        sql += " WHERE status = 'ready'"
    with tenant_tx(tenant_id) as conn:
        rows = conn.execute(sql + " ORDER BY created_at DESC").fetchall()
    return [_doc(r) for r in rows]


def mark_document_processing(tenant_id: str, document_id: str, *, file_name: str) -> None:
    with tenant_tx(tenant_id) as conn:
        conn.execute(
            "UPDATE documents SET status = 'processing', error = NULL, file_name = %s, updated_at = now()"
            " WHERE id = %s",
            (file_name, document_id),
        )


def mark_document_failed(tenant_id: str, document_id: str, error: str) -> None:
    with tenant_tx(tenant_id) as conn:
        conn.execute(
            "UPDATE documents SET status = 'failed', error = %s, updated_at = now() WHERE id = %s",
            (error[:2000], document_id),
        )


def mark_document_ready(
    tenant_id: str,
    document_id: str,
    *,
    page_count: int,
    model_key: str | None,
    ledger: list[dict[str, Any]],
    domain_hint: str = "",
    stats: dict[str, Any] | None = None,
) -> None:
    """Write the page ledger and flip the document to ``ready`` in one transaction."""
    needing_review = sum(1 for p in ledger if p.get("needs_review"))
    rows = [
        (
            document_id,
            int(p["page"]),
            str(p.get("engine") or "none"),
            float(p.get("confidence") or 0.0),
            Jsonb(list(p.get("flags") or [])),
            bool(p.get("needs_review")),
            float(p.get("seconds") or 0.0),
            float(p.get("cost_usd") or 0.0),
        )
        for p in ledger
    ]
    with tenant_tx(tenant_id) as conn:
        conn.execute("DELETE FROM pages WHERE document_id = %s", (document_id,))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO pages (document_id, number, engine, confidence, flags, needs_review, seconds, cost_usd)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                rows,
            )
        conn.execute(
            "UPDATE documents SET status = 'ready', error = NULL, page_count = %s, model_key = %s,"
            " pages_needing_review = %s, domain_hint = %s, stats = %s, updated_at = now() WHERE id = %s",
            (page_count, model_key, needing_review, domain_hint, Jsonb(stats or {}), document_id),
        )


def page_ledger(tenant_id: str, document_id: str) -> list[dict[str, Any]]:
    did = as_uuid(document_id)
    if did is None:
        return []
    with tenant_tx(tenant_id) as conn:
        rows = conn.execute(
            "SELECT number, engine, confidence, flags, needs_review, seconds, cost_usd FROM pages"
            " WHERE document_id = %s ORDER BY number",
            (did,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- Chat threads ----------------------------------------------------------------

_THREAD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class ThreadRow:
    id: str
    user_id: str
    document_id: str | None
    title: str
    message_count: int
    updated_at: datetime


def _thread(row: dict | None) -> ThreadRow | None:
    if row is None:
        return None
    return ThreadRow(
        id=row["id"],
        user_id=str(row["user_id"]),
        document_id=str(row["document_id"]) if row["document_id"] else None,
        title=row["title"],
        message_count=row["message_count"],
        updated_at=row["updated_at"],
    )


def valid_thread_id(thread_id: str) -> bool:
    return bool(thread_id) and bool(_THREAD_ID.match(thread_id))


def claim_thread(principal: Principal, thread_id: str, document_id: str | None = None) -> ThreadRow:
    """Create the thread for this user, or confirm they already own it.

    A thread that belongs to another user (or does not pass validation) is
    reported as not found. Ownership never moves. A document pin is updated
    when one is given.
    """
    if not valid_thread_id(thread_id):
        raise AccessDeniedError(f"Thread {thread_id!r} not found.")
    did = as_uuid(document_id) if document_id else None
    with tenant_tx(principal.tenant_id) as conn:
        conn.execute(
            "INSERT INTO threads (id, user_id, document_id) VALUES (%s, %s, %s)"
            " ON CONFLICT (tenant_id, id) DO NOTHING",
            (thread_id, principal.user_id, did),
        )
        row = conn.execute(
            "SELECT id, user_id, document_id, title, message_count, updated_at FROM threads WHERE id = %s",
            (thread_id,),
        ).fetchone()
        if row is None or str(row["user_id"]) != principal.user_id:
            raise AccessDeniedError(f"Thread {thread_id!r} not found.")
        if did and str(row["document_id"] or "") != did:
            row = conn.execute(
                "UPDATE threads SET document_id = %s, updated_at = now() WHERE id = %s"
                " RETURNING id, user_id, document_id, title, message_count, updated_at",
                (did, thread_id),
            ).fetchone()
    return _thread(row)


def get_thread(principal: Principal, thread_id: str) -> ThreadRow:
    """The caller's own thread; anything else is not found (fail closed)."""
    if not valid_thread_id(thread_id):
        raise AccessDeniedError(f"Thread {thread_id!r} not found.")
    with tenant_tx(principal.tenant_id) as conn:
        row = conn.execute(
            "SELECT id, user_id, document_id, title, message_count, updated_at FROM threads"
            " WHERE id = %s AND user_id = %s",
            (thread_id, principal.user_id),
        ).fetchone()
    if row is None:
        raise AccessDeniedError(f"Thread {thread_id!r} not found.")
    return _thread(row)


def record_turn(principal: Principal, thread_id: str, *, question: str, messages_added: int = 2) -> None:
    title = question.strip()
    title = title[:60] + ("..." if len(title) > 60 else "")
    with tenant_tx(principal.tenant_id) as conn:
        conn.execute(
            "UPDATE threads SET message_count = message_count + %s,"
            " title = CASE WHEN title = '' THEN %s ELSE title END, updated_at = now()"
            " WHERE id = %s AND user_id = %s",
            (messages_added, title, thread_id, principal.user_id),
        )


def list_threads(principal: Principal) -> list[ThreadRow]:
    with tenant_tx(principal.tenant_id) as conn:
        rows = conn.execute(
            "SELECT id, user_id, document_id, title, message_count, updated_at FROM threads"
            " WHERE user_id = %s AND message_count > 0 ORDER BY updated_at DESC",
            (principal.user_id,),
        ).fetchall()
    return [_thread(r) for r in rows]
