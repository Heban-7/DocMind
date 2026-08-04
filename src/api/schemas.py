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
    federated_search: bool = Field(
        default=False,
        description="Search across entire document library regardless of pin",
    )
    audit_mode: bool = Field(
        default=False,
        description="Enforce strict zero-trust audit verification mode",
    )
    model: Optional[str] = Field(
        default="gpt-4o",
        description="Selected LLM model for generation (e.g. gpt-4o, gemini-1.5-pro)",
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
    document_id: Optional[str] = None
    document_info: Optional[DocumentInfo] = None


class ThreadSummary(BaseModel):
    thread_id: str
    title: str
    message_count: int
    document_id: Optional[str] = None
    document_info: Optional[DocumentInfo] = None


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

