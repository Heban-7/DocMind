"""FastAPI request / response contracts for the DocMind API gateway."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    version: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, description="User question or follow-up")
    thread_id: str = Field(min_length=1, description="Conversation / session id")
    document_id: Optional[str] = Field(
        default=None,
        description="Pin one document; omit for IntentRouter / corpus search",
    )


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class UploadResponse(BaseModel):
    document_id: str
    file_name: str
    page_count: int
    strategy_tier: str
    status: str


class HistoryMessage(BaseModel):
    role: str
    content: str


class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[HistoryMessage] = Field(default_factory=list)


class ThreadSummary(BaseModel):
    thread_id: str
    title: str
    message_count: int


class ThreadListResponse(BaseModel):
    threads: list[ThreadSummary] = Field(default_factory=list)


class DocumentInfo(BaseModel):
    document_id: str
    file_name: str
    page_count: int
    strategy_tier: str
    status: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo] = Field(default_factory=list)

