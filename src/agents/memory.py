"""Conversation memory: LangGraph checkpoints in Postgres.

The checkpoint tables carry no tenant column, so they are reached only with a
key built from the caller's tenant and an already-authorised thread id:
``<tenant_id>:<thread_id>``. Two tenants using the same thread id therefore
never share a conversation, even if an ownership check were skipped.
"""

from __future__ import annotations

import threading

from langgraph.checkpoint.base import BaseCheckpointSaver

from src.models.conversation import ConversationMessage, MessageRole

_saver: BaseCheckpointSaver | None = None
_lock = threading.Lock()


def checkpoint_key(tenant_id: str, thread_id: str) -> str:
    return f"{tenant_id}:{thread_id}"


def postgres_checkpointer() -> BaseCheckpointSaver:
    """The process-wide PostgresSaver (tables are created by ``src.db.migrate``)."""
    global _saver
    with _lock:
        # A closed pool (app shutdown, tests) means a new pool and a new saver.
        if _saver is None or getattr(_saver.conn, "closed", False):
            from langgraph.checkpoint.postgres import PostgresSaver

            from src.db.pool import get_checkpoint_pool

            _saver = PostgresSaver(get_checkpoint_pool())
        return _saver


def reset_checkpointer() -> None:
    global _saver
    with _lock:
        _saver = None


def read_messages(saver: BaseCheckpointSaver, key: str) -> list[ConversationMessage]:
    """The stored turns of one conversation, without building an agent."""
    tup = saver.get_tuple({"configurable": {"thread_id": key, "checkpoint_ns": ""}})
    if tup is None:
        return []
    raw = list((tup.checkpoint.get("channel_values") or {}).get("messages") or [])
    out: list[ConversationMessage] = []
    for msg in raw:
        content = str(getattr(msg, "content", "") or "").strip()
        if not content:
            continue
        mtype = getattr(msg, "type", "")
        role = {"human": MessageRole.USER, "ai": MessageRole.ASSISTANT}.get(mtype, MessageRole.SYSTEM)
        out.append(ConversationMessage(role=role, content=content))
    return out
