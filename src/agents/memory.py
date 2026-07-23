"""
LangGraph conversation checkpointer (STEP 1 -- Patient File).

Persists graph state (including ``messages``) to SQLite keyed by ``thread_id``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver

from src.config import CHECKPOINTS_DB_PATH


def build_sqlite_checkpointer(
    db_path: str | Path | None = None,
) -> SqliteSaver:
    """Open (or create) a SQLite checkpointer and ensure its schema exists.

    Keeps a long-lived connection with ``check_same_thread=False`` so the
    agent can be called from CLI / web workers safely.
    """
    path = Path(db_path) if db_path is not None else CHECKPOINTS_DB_PATH
    conn_str = ":memory:" if str(path) == ":memory:" else str(path)
    if conn_str != ":memory:":
        Path(conn_str).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(conn_str, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def ensure_checkpointer(
    checkpointer: BaseCheckpointSaver | None = None,
    *,
    db_path: str | Path | None = None,
) -> BaseCheckpointSaver:
    """Return the given checkpointer, or build the default SQLite one."""
    if checkpointer is not None:
        return checkpointer
    return build_sqlite_checkpointer(db_path)
