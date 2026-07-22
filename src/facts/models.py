"""
FactTable contracts -- structured numerical claims pulled from LDUs.

These rows power ``structured_query``: precise answers like "what was FY 2020/21
import tax expenditure?" without asking an LLM to invent a number.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class FactRecord(BaseModel):
    """One extracted key-value numerical / fiscal fact with provenance hooks."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doc_id: str
    document_name: str = ""
    metric: str = Field(description="what was measured, e.g. 'import tax expenditures'")
    value: float | None = Field(
        default=None, description="parsed numeric value when available"
    )
    value_text: str = Field(description="original value string as seen in the source")
    unit: str = Field(default="", description="e.g. ETB billion, %, USD")
    period: str = Field(default="", description="e.g. FY 2020/21, Q3 2024")
    page_number: int = Field(ge=1, default=1)
    content_hash: str = ""
    chunk_id: str = ""
    source_excerpt: str = Field(
        default="", description="short supporting span from the LDU"
    )
    extractor: str = Field(
        default="heuristic",
        description="heuristic | llm -- how this row was produced",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
