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
        self._context: dict[str, str] = {}
        self._embed_hash: dict[str, str] = {}

    def count(self, doc_id: str | None = None) -> int:
        return sum(1 for r in self._rows.values() if doc_id is None or r[0] == doc_id)

    def delete_doc(self, doc_id: str) -> None:
        self._rows = {k: v for k, v in self._rows.items() if v[0] != doc_id}

    def replace_doc_chunks(self, doc_id, chunks, embeddings, *, document_name="", contexts=None, embed_hashes=None) -> int:
        if embeddings is not None and len(chunks) != len(embeddings):
            raise ValueError(f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) length mismatch")
        self.delete_doc(doc_id)
        for i, c in enumerate(chunks):
            vec = list(embeddings[i]) if embeddings is not None else None
            self._rows[c.id] = (doc_id, document_name or doc_id, c, vec)
            self._context[c.id] = contexts[i] if contexts else ""
            self._embed_hash[c.id] = embed_hashes[i] if embed_hashes else c.metadata.content_hash
        return len(chunks)

    def existing_embeddings(self, doc_id: str) -> dict[str, list[float]]:
        return {
            self._embed_hash.get(c.id, c.metadata.content_hash): list(e)
            for d, _, c, e in self._rows.values()
            if d == doc_id and e is not None
        }

    def search(self, query_text, query_embedding, *, doc_id=None, top_k=20) -> list[RetrievedChunk]:
        """Vector and keyword ranks fused with reciprocal rank fusion, like the Postgres store."""
        from src.retrieval.keywords import keyword_overlap

        rows = [r for r in self._rows.values() if doc_id is None or r[0] == doc_id]
        fused: dict[str, float] = {}
        if query_embedding is not None:
            ranked = sorted((r for r in rows if r[3] is not None), key=lambda r: _cosine_distance(query_embedding, r[3]))
            for rank, r in enumerate(ranked[:40], start=1):
                fused[r[2].id] = fused.get(r[2].id, 0.0) + 1.0 / (60 + rank)
        kw = sorted(
            ((keyword_overlap(query_text, self._context.get(r[2].id, "") + " " + r[2].text), r) for r in rows),
            key=lambda t: -t[0],
        )
        for rank, (score, r) in enumerate([t for t in kw if t[0] > 0][:40], start=1):
            fused[r[2].id] = fused.get(r[2].id, 0.0) + 1.0 / (60 + rank)
        best = sorted(fused.items(), key=lambda t: -t[1])[:top_k]
        out = []
        for cid, f in best:
            d, name, c, e = self._rows[cid]
            dist = _cosine_distance(query_embedding, e) if (query_embedding is not None and e is not None) else 1.0
            out.append(
                RetrievedChunk(
                    chunk_id=c.id, text=c.text, doc_id=d, document_name=name,
                    page_numbers=list(c.metadata.page_numbers), parent_hierarchy=list(c.metadata.parent_hierarchy),
                    content_hash=c.metadata.content_hash, chunk_type=c.metadata.chunk_type, distance=dist,
                    context=self._context.get(c.id, ""), relevance=round(f * 30.5, 4),
                )
            )
        return out

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
            and (not metric_contains or metric_contains.lower() in " ".join([f.row_group, f.metric, f.column_label, f.table_title]).lower())
            and (not period_contains or period_contains.lower() in f.period.lower())
        ]
        return sorted(out, key=lambda f: (f.page_number, f.metric))[:limit]

    def run_query(self, spec, *, doc_id=None):
        """The FactQuery semantics in Python (the Postgres store does it in SQL)."""
        from src.facts.query import run_in_memory

        return run_in_memory(self._facts, spec, doc_id=doc_id)


class MemoryPageIndexStore:
    def __init__(self) -> None:
        self._indexes: dict[str, PageIndex] = {}

    def save(self, index: PageIndex) -> None:
        self._indexes[index.doc_id] = index

    def load(self, doc_id: str) -> PageIndex | None:
        return self._indexes.get(doc_id)


def memory_stores() -> Stores:
    return Stores(chunks=MemoryChunkStore(), facts=MemoryFactStore(), pageindex=MemoryPageIndexStore())
