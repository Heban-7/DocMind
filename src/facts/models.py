"""
FactTable contracts: typed numbers read from tables and text.

A fact keeps the number exactly as printed (``value_text``), its signed value
before scale (``value``), the scale and unit the document states for it, the
labels that say what it measures, and where it is (page, table cell, box), so
questions about numbers can be answered by the database instead of the LLM.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class FactRecord(BaseModel):
    """One number from a document, with what it measures and where it is printed."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doc_id: str
    document_name: str = ""
    metric: str = Field(description="what was measured: the row label, or the words before a number in text")
    value: float | None = Field(default=None, description="signed value as printed, before scale")
    value_text: str = Field(description="the number exactly as printed")
    unit: str = Field(default="", description="currency code or unit: ETB, USD, %, ...")
    period: str = Field(default="", description="e.g. FY 2020/21, 2023/24, March EFY2017")
    page_number: int = Field(ge=1, default=1)
    content_hash: str = ""
    chunk_id: str = ""
    source_excerpt: str = Field(default="", description="short supporting text")
    extractor: str = Field(default="heuristic", description="typed-table | typed-text | heuristic | llm")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Typed fields (M5)
    row_label: str = ""
    row_group: str = Field(default="", description="the section row above, e.g. 'Operating expenses'")
    column_label: str = ""
    table_title: str = ""
    scale: float = Field(default=1.0, description="multiplier the document states, e.g. 1e6 for 'in ETB million'")
    currency: str = ""
    table_id: str = ""
    row_index: int | None = None
    col_index: int | None = None
    bbox: list[float] | None = Field(default=None, description="[x0, top, x1, bottom], PDF points, top-left origin")
    source: str = Field(default="text", description="table | text")
    confidence: float = 1.0
    period_key: str = Field(default="", description="normalised period for matching: 2020/21, march 2017, 2023")

    @property
    def absolute_value(self) -> float | None:
        return None if self.value is None else self.value * self.scale
