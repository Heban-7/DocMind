"""FastAPI request / response contracts for the DocMind API gateway."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    version: str


# ── Auth schemas ──────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=100, description="User email address")
    password: str = Field(min_length=6, description="Password (min 6 characters)")


class UserLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: str
    email: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000, description="User question or follow-up")
    thread_id: str = Field(min_length=1, max_length=200, description="Conversation / session id")
    document_id: Optional[str] = Field(
        default=None,
        description="Pin one document; omit to let the planner pick from your documents",
    )
    federated_search: bool = Field(
        default=False,
        description="Search across entire document library regardless of pin",
    )
    audit_mode: bool = Field(
        default=False,
        description="Audit Mode: check a claim, or answer with every sentence cited; anything uncited is removed",
    )
    mode: Optional[str] = Field(
        default=None,
        description="Answer length: concise | balanced (default) | detailed. Audit Mode overrides it.",
    )
    model: Optional[str] = Field(
        default=None,
        max_length=120,
        description="A model id from GET /api/models; omit for the server default",
    )


class AnswerUsage(BaseModel):
    """The answer footer: which model wrote it, how long it took, what it cost."""

    model: str = ""
    provider: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    first_token_s: float | None = None


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    follow_ups: list[str] = Field(
        default_factory=list,
        description="Autonomous follow-up questions suggested by the AI.",
    )
    status: str = Field(default="answered", description="answered | not_found | greeting")
    mode: str = "balanced"
    prompt_profile: str = ""
    usage: AnswerUsage = Field(default_factory=AnswerUsage)
    verification: dict[str, Any] = Field(default_factory=dict, description="sentence-by-sentence evidence check")


class UploadResponse(BaseModel):
    document_id: str
    file_name: str
    page_count: int
    strategy_tier: str
    status: str = Field(description="queued | processing | indexed (ready) | failed")
    pages_needing_review: int = 0
    deduplicated: bool = Field(default=False, description="Same file was already in this account")
    stage: str = ""
    pages_done: int = 0
    progress: float = Field(default=0.0, description="0-1, pages read so far")
    searchable: bool = False


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
    status: str = Field(description="queued | processing | indexed (ready) | failed")
    pages_needing_review: int = 0
    stage: str = Field(default="", description="queued | reading | layout | indexing | done | retrying | failed")
    pages_done: int = 0
    progress: float = Field(default=0.0, description="0-1, pages read so far")
    searchable: bool = Field(default=False, description="Questions can already use this document")
    error: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo] = Field(default_factory=list)

