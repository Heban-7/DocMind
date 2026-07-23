"""
Evidence objects returned by Query Agent tools.

Tools never invent answers -- they return *evidence*. The agent (Step 7) and
provenance assembler (Step 6) turn these hits into a cited QueryAnswer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.models.query import ToolName, ToolTrace


class EvidenceHit(BaseModel):
    """One piece of retrieval evidence with enough fields for a Citation."""

    model_config = ConfigDict(frozen=True)

    tool: ToolName
    document_name: str = ""
    doc_id: str = ""
    page_number: int = Field(ge=1, default=1)
    printed_page: str | None = Field(
        default=None,
        description="optional document/printed page label when known",
    )
    content_hash: str = ""
    chunk_id: str | None = None
    excerpt: str = ""
    title: str = Field(
        default="",
        description="section title / metric name / other short label",
    )
    score: float = Field(
        default=0.0, description="relevance score when available (higher better)"
    )
    extra: dict = Field(
        default_factory=dict,
        description="tool-specific payload (path, unit, period, distance, ...)",
    )


class ToolResult(BaseModel):
    """Bundle returned by every tool: hits + a ToolTrace for the agent log."""

    model_config = ConfigDict(frozen=True)

    tool: ToolName
    hits: list[EvidenceHit] = Field(default_factory=list)
    trace: ToolTrace

    @property
    def is_empty(self) -> bool:
        return len(self.hits) == 0
