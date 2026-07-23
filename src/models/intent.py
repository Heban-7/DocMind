"""
Intent routing contracts for multi-document federated search (STEP 2).

The IntentRouter is the Librarian's decision slip: either point at one shelf
(document_id) or walk the whole library (document_id=None).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SearchScope(str, Enum):
    """Whether retrieval is pinned to one document or the whole corpus."""

    SINGLE_DOCUMENT = "single_document"
    CORPUS = "corpus"


class CorpusDocument(BaseModel):
    """One searchable document known to the refinery."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1)
    document_name: str = ""
    domain_hint: str = ""
    page_count: int | None = None


class IntentRouter(BaseModel):
    """LLM (or heuristic) output that steers retrieval metadata filters.

    ``document_id``:
      - a concrete id  -> Chroma ``where={"doc_id": ...}`` (strict filter)
      - ``None``       -> corpus-wide search (no doc_id filter)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str | None = Field(
        default=None,
        description="Target doc id, or None for corpus-wide search.",
    )
    scope: SearchScope = Field(
        default=SearchScope.CORPUS,
        description="Derived scope; must agree with document_id.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Router confidence in the chosen scope.",
    )
    rationale: str = Field(
        default="",
        description="Short explanation of why this document (or corpus) was chosen.",
    )

    @model_validator(mode="after")
    def _align_scope_with_document_id(self) -> IntentRouter:
        if self.document_id:
            object.__setattr__(self, "scope", SearchScope.SINGLE_DOCUMENT)
        else:
            object.__setattr__(self, "scope", SearchScope.CORPUS)
        return self

    @property
    def is_corpus_wide(self) -> bool:
        return self.document_id is None
