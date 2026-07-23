"""
Conversation / session contracts for Query Agent memory (STEP 1).

A thread_id is the patient's chart number: the same id resumes the same
conversation. Messages are the dated entries on that chart.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationMessage(BaseModel):
    """One turn in a persisted conversation (API / display form)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: MessageRole
    content: str = Field(min_length=1)


class SessionConfig(BaseModel):
    """LangGraph runnable config for a memory-backed thread."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: str = Field(
        min_length=1,
        description="Stable conversation id (e.g. user-session UUID).",
    )

    def to_runnable_config(self) -> dict:
        """Shape expected by LangGraph ``invoke(..., config=...)``."""
        return {"configurable": {"thread_id": self.thread_id}}
