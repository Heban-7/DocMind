"""Connection pool and tenant-scoped transactions.

Every application connection switches to the ``docmind_app`` role, which has
no superuser rights, so Postgres row-level security applies. ``tenant_tx``
opens a transaction with ``app.tenant_id`` set for that transaction only; a
query outside it sees no tenant rows at all (fail closed).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DEFAULT_URL = "postgresql://docmind:docmind-dev-only@localhost:5433/docmind"
APP_ROLE = "docmind_app"

_pool: ConnectionPool | None = None
_checkpoint_pool: ConnectionPool | None = None
_lock = threading.Lock()
_atexit_registered = False


def _close_at_exit() -> None:
    """Close pools when a script ends; otherwise each worker thread stalls exit."""
    global _atexit_registered
    if not _atexit_registered:
        import atexit

        atexit.register(close_pool)
        _atexit_registered = True


def database_url() -> str:
    return os.getenv("DOCMIND_DATABASE_URL", DEFAULT_URL)


def _configure(conn: psycopg.Connection) -> None:
    from pgvector.psycopg import register_vector

    conn.execute(f"SET ROLE {APP_ROLE}")
    register_vector(conn)
    conn.commit()


def _configure_checkpoint(conn: psycopg.Connection) -> None:
    conn.execute(f"SET ROLE {APP_ROLE}")


def get_checkpoint_pool() -> ConnectionPool:
    """Pool for LangGraph's PostgresSaver, which needs autocommit connections."""
    global _checkpoint_pool
    with _lock:
        if _checkpoint_pool is None:
            _close_at_exit()
            _checkpoint_pool = ConnectionPool(
                database_url(),
                min_size=1,
                max_size=int(os.getenv("DOCMIND_DB_POOL_SIZE", "8")),
                kwargs={"row_factory": dict_row, "autocommit": True, "prepare_threshold": 0},
                configure=_configure_checkpoint,
                open=True,
            )
        return _checkpoint_pool


def get_pool() -> ConnectionPool:
    global _pool
    with _lock:
        if _pool is None:
            _close_at_exit()
            _pool = ConnectionPool(
                database_url(),
                min_size=1,
                max_size=int(os.getenv("DOCMIND_DB_POOL_SIZE", "8")),
                kwargs={"row_factory": dict_row, "autocommit": False},
                configure=_configure,
                open=True,
            )
        return _pool


def close_pool() -> None:
    global _pool, _checkpoint_pool
    with _lock:
        for pool in (_pool, _checkpoint_pool):
            if pool is not None:
                pool.close()
        _pool = None
        _checkpoint_pool = None


def database_available(timeout: int = 2) -> bool:
    """True when the configured database accepts connections (used by tests)."""
    try:
        with psycopg.connect(database_url(), connect_timeout=timeout):
            return True
    except psycopg.Error:
        return False


@contextmanager
def tenant_tx(tenant_id: str | UUID) -> Iterator[psycopg.Connection]:
    """One transaction in which every query sees only ``tenant_id``'s rows."""
    tid = str(UUID(str(tenant_id)))  # raises on anything that is not a UUID
    with get_pool().connection() as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tid,))
            yield conn


@contextmanager
def app_tx() -> Iterator[psycopg.Connection]:
    """A transaction with no tenant set: only tables without RLS are visible."""
    with get_pool().connection() as conn:
        with conn.transaction():
            yield conn


@contextmanager
def admin_connection() -> Iterator[psycopg.Connection]:
    """A direct connection as the database owner, for migrations only."""
    url = os.getenv("DOCMIND_DATABASE_ADMIN_URL", database_url())
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as conn:
        yield conn
