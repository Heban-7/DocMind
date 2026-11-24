"""The storage interfaces the query side depends on."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.chunking.models import DocumentChunk
from src.facts.models import FactRecord
from src.models.page_index import PageIndex


@dataclass
class RetrievedChunk:
    """One retrieval hit with score and provenance fields."""

    chunk_id: str
    text: str
    doc_id: str
    document_name: str
    page_numbers: list[int]
    parent_hierarchy: list[str]
    content_hash: str
    chunk_type: str
    distance: float  # cosine distance: lower is closer (1.0 when only the keyword search found it)
    context: str = ""  # document title and section path, embedded and searched with the text
    relevance: float | None = None  # fused or reranked relevance in [0, 1], when hybrid search ran

    @property
    def score(self) -> float:
        """Relevance in [0, 1]: the reranker's or fused score, else 1 / (1 + distance)."""
        if self.relevance is not None:
            return self.relevance
        return 1.0 / (1.0 + max(self.distance, 0.0))


class ChunkStore(Protocol):
    def replace_doc_chunks(
        self,
        doc_id: str,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]] | None,
        *,
        document_name: str = "",
        contexts: list[str] | None = None,
        embed_hashes: list[str] | None = None,
    ) -> int: ...

    def delete_doc(self, doc_id: str) -> None: ...

    def existing_embeddings(self, doc_id: str) -> dict[str, list[float]]: ...  # by embed hash

    def query(self, query_embedding: list[float], *, doc_id: str | None = None, top_k: int = 7) -> list[RetrievedChunk]: ...

    def search(
        self, query_text: str, query_embedding: list[float] | None, *, doc_id: str | None = None, top_k: int = 20
    ) -> list[RetrievedChunk]: ...  # hybrid: vectors + keywords, fused

    def count(self, doc_id: str | None = None) -> int: ...


class FactStore(Protocol):
    def replace_doc_facts(self, doc_id: str, facts: list[FactRecord]) -> int: ...

    def search(
        self,
        *,
        doc_id: str | None = None,
        metric_contains: str | None = None,
        period_contains: str | None = None,
        limit: int = 50,
    ) -> list[FactRecord]: ...

    def count(self, doc_id: str | None = None) -> int: ...

    def run_query(self, spec, *, doc_id: str | None = None): ...  # FactQuery -> FactQueryResult


class PageIndexStore(Protocol):
    def save(self, index: PageIndex) -> None: ...

    def load(self, doc_id: str) -> PageIndex | None: ...


@dataclass
class Stores:
    """The three stores one tenant's queries run against."""

    chunks: ChunkStore
    facts: FactStore
    pageindex: PageIndexStore
