"""In-memory stores for unit tests and the offline demo. Not for production."""

from __future__ import annotations

import math

from src.chunking.models import DocumentChunk
from src.facts.models import FactRecord
from src.models.page_index import PageIndex
from src.stores.base import RetrievedChunk, Stores


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return 1.0 - dot / (na * nb)


class MemoryChunkStore:
    def __init__(self) -> None:
        # chunk id -> (doc_id, document_name, chunk, embedding or None)
        self._rows: dict[str, tuple[str, str, DocumentChunk, list[float] | None]] = {}

    def count(self, doc_id: str | None = None) -> int:
        return sum(1 for r in self._rows.values() if doc_id is None or r[0] == doc_id)

    def delete_doc(self, doc_id: str) -> None:
        self._rows = {k: v for k, v in self._rows.items() if v[0] != doc_id}

    def replace_doc_chunks(self, doc_id, chunks, embeddings, *, document_name="") -> int:
        if embeddings is not None and len(chunks) != len(embeddings):
            raise ValueError(f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) length mismatch")
        self.delete_doc(doc_id)
        for i, c in enumerate(chunks):
            vec = list(embeddings[i]) if embeddings is not None else None
            self._rows[c.id] = (doc_id, document_name or doc_id, c, vec)
        return len(chunks)

    def existing_embeddings(self, doc_id: str) -> dict[str, list[float]]:
        return {c.metadata.content_hash: list(e) for d, _, c, e in self._rows.values() if d == doc_id and e is not None}

    def query(self, query_embedding, *, doc_id=None, top_k=7) -> list[RetrievedChunk]:
        rows = [r for r in self._rows.values() if r[3] is not None and (doc_id is None or r[0] == doc_id)]
        scored = sorted(((_cosine_distance(query_embedding, r[3]), r) for r in rows), key=lambda t: t[0])[:top_k]
        return [
            RetrievedChunk(
                chunk_id=c.id,
                text=c.text,
                doc_id=d,
                document_name=name,
                page_numbers=list(c.metadata.page_numbers),
                parent_hierarchy=list(c.metadata.parent_hierarchy),
                content_hash=c.metadata.content_hash,
                chunk_type=c.metadata.chunk_type,
                distance=dist,
            )
            for dist, (d, name, c, _) in scored
        ]


class MemoryFactStore:
    def __init__(self) -> None:
        self._facts: list[FactRecord] = []

    def replace_doc_facts(self, doc_id: str, facts: list[FactRecord]) -> int:
        self._facts = [f for f in self._facts if f.doc_id != doc_id] + list(facts)
        return len(facts)

    def count(self, doc_id: str | None = None) -> int:
        return sum(1 for f in self._facts if doc_id is None or f.doc_id == doc_id)

    def search(self, *, doc_id=None, metric_contains=None, period_contains=None, limit=50) -> list[FactRecord]:
        out = [
            f
            for f in self._facts
            if (doc_id is None or f.doc_id == doc_id)
            and (not metric_contains or metric_contains.lower() in f.metric.lower())
            and (not period_contains or period_contains.lower() in f.period.lower())
        ]
        return sorted(out, key=lambda f: (f.page_number, f.metric))[:limit]


class MemoryPageIndexStore:
    def __init__(self) -> None:
        self._indexes: dict[str, PageIndex] = {}

    def save(self, index: PageIndex) -> None:
        self._indexes[index.doc_id] = index

    def load(self, doc_id: str) -> PageIndex | None:
        return self._indexes.get(doc_id)


def memory_stores() -> Stores:
    return Stores(chunks=MemoryChunkStore(), facts=MemoryFactStore(), pageindex=MemoryPageIndexStore())
