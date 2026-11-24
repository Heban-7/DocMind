"""Postgres stores. Every query runs inside ``tenant_tx``, so row-level security
limits it to one tenant's rows; the stores never filter by tenant themselves.

Only documents marked ``searchable`` are searched: a document becomes
searchable once its first quick index is complete (see src/pipeline/ingest.py),
never while its chunks are half written.
"""

from __future__ import annotations

from uuid import UUID

import numpy as np
from psycopg.types.json import Jsonb

from src.chunking.models import DocumentChunk
from src.db.pool import tenant_tx
from src.facts.models import FactRecord
from src.models.page_index import PageIndex
from src.stores.base import RetrievedChunk, Stores


def as_uuid(value: str | UUID | None) -> str | None:
    """The canonical UUID string, or None for anything that is not a UUID."""
    if value is None:
        return None
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def _vec(values) -> np.ndarray:
    return np.asarray(values, dtype=np.float32)


class _TenantBound:
    def __init__(self, tenant_id: str | UUID):
        tid = as_uuid(tenant_id)
        if tid is None:
            raise ValueError("tenant_id must be a UUID")
        self.tenant_id = tid


class PgChunkStore(_TenantBound):
    def count(self, doc_id: str | None = None) -> int:
        with tenant_tx(self.tenant_id) as conn:
            if doc_id is None:
                row = conn.execute("SELECT count(*) AS n FROM chunks").fetchone()
            else:
                did = as_uuid(doc_id)
                if did is None:
                    return 0
                row = conn.execute("SELECT count(*) AS n FROM chunks WHERE document_id = %s", (did,)).fetchone()
        return int(row["n"])

    def delete_doc(self, doc_id: str) -> None:
        did = as_uuid(doc_id)
        if did is None:
            return
        with tenant_tx(self.tenant_id) as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (did,))

    def replace_doc_chunks(self, doc_id, chunks: list[DocumentChunk], embeddings, *, document_name: str = "") -> int:
        did = as_uuid(doc_id)
        if did is None:
            raise ValueError("doc_id must be a UUID")
        if embeddings is not None and len(chunks) != len(embeddings):
            raise ValueError(f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) length mismatch")
        rows = [
            (
                c.id,
                did,
                i,
                c.text,
                c.metadata.chunk_type,
                list(c.metadata.parent_hierarchy),
                list(c.metadata.page_numbers),
                c.metadata.content_hash,
                c.metadata.word_count,
                _vec(embeddings[i]) if embeddings is not None else None,
            )
            for i, c in enumerate(chunks)
        ]
        with tenant_tx(self.tenant_id) as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (did,))
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunks (id, document_id, ordinal, text, chunk_type, section_path, page_numbers,"
                    " content_hash, word_count, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )
        return len(rows)

    def existing_embeddings(self, doc_id: str) -> dict[str, list[float]]:
        """Vectors already stored for this document, by chunk content hash."""
        did = as_uuid(doc_id)
        if did is None:
            return {}
        with tenant_tx(self.tenant_id) as conn:
            rows = conn.execute(
                "SELECT DISTINCT ON (content_hash) content_hash, embedding FROM chunks"
                " WHERE document_id = %s AND embedding IS NOT NULL",
                (did,),
            ).fetchall()
        out: dict[str, list[float]] = {}
        for r in rows:
            v = r["embedding"]  # a pgvector Vector, or a numpy array, depending on the adapter
            out[r["content_hash"]] = [float(x) for x in (v.to_list() if hasattr(v, "to_list") else v)]
        return out

    def query(self, query_embedding, *, doc_id: str | None = None, top_k: int = 7) -> list[RetrievedChunk]:
        params: list = [_vec(query_embedding)]
        where = "d.searchable AND c.embedding IS NOT NULL"
        if doc_id is not None:
            did = as_uuid(doc_id)
            if did is None:
                return []
            where += " AND c.document_id = %s"
            params.append(did)
        params.append(int(top_k))
        sql = (
            "SELECT c.id, c.text, c.document_id, d.file_name, c.page_numbers, c.section_path, c.content_hash,"
            " c.chunk_type, c.embedding <=> q.v AS distance"
            " FROM chunks c JOIN documents d ON d.id = c.document_id, (SELECT %s::vector AS v) q"
            f" WHERE {where} ORDER BY c.embedding <=> q.v LIMIT %s"
        )
        with tenant_tx(self.tenant_id) as conn:
            # With a document filter the HNSW scan keeps going until it has
            # top_k rows that pass the filter (pgvector >= 0.8).
            conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            rows = conn.execute(sql, params).fetchall()
        hits = [
            RetrievedChunk(
                chunk_id=str(r["id"]),
                text=r["text"],
                doc_id=str(r["document_id"]),
                document_name=r["file_name"],
                page_numbers=list(r["page_numbers"] or [1]),
                parent_hierarchy=list(r["section_path"] or []),
                content_hash=r["content_hash"],
                chunk_type=r["chunk_type"],
                distance=float(r["distance"]),
            )
            for r in rows
        ]
        return sorted(hits, key=lambda h: h.distance)


_FACT_COLUMNS = (
    "id, document_id, metric, value, value_text, unit, period, page_number, content_hash, chunk_id,"
    " source_excerpt, extractor, created_at"
)


class PgFactStore(_TenantBound):
    def replace_doc_facts(self, doc_id: str, facts: list[FactRecord]) -> int:
        did = as_uuid(doc_id)
        if did is None:
            raise ValueError("doc_id must be a UUID")
        rows = [
            (
                f.id,
                did,
                f.metric,
                f.value,
                f.value_text,
                f.unit,
                f.period,
                f.page_number,
                f.content_hash,
                f.chunk_id,
                f.source_excerpt,
                f.extractor,
                f.created_at,
            )
            for f in facts
        ]
        with tenant_tx(self.tenant_id) as conn:
            conn.execute("DELETE FROM facts WHERE document_id = %s", (did,))
            with conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO facts ({_FACT_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )
        return len(rows)

    def count(self, doc_id: str | None = None) -> int:
        with tenant_tx(self.tenant_id) as conn:
            if doc_id is None:
                row = conn.execute("SELECT count(*) AS n FROM facts").fetchone()
            else:
                did = as_uuid(doc_id)
                if did is None:
                    return 0
                row = conn.execute("SELECT count(*) AS n FROM facts WHERE document_id = %s", (did,)).fetchone()
        return int(row["n"])

    def search(self, *, doc_id=None, metric_contains=None, period_contains=None, limit=50) -> list[FactRecord]:
        clauses = ["d.searchable"]
        params: list = []
        if doc_id is not None:
            did = as_uuid(doc_id)
            if did is None:
                return []
            clauses.append("f.document_id = %s")
            params.append(did)
        if metric_contains:
            clauses.append("f.metric ILIKE %s")
            params.append(f"%{_escape_like(metric_contains)}%")
        if period_contains:
            clauses.append("f.period ILIKE %s")
            params.append(f"%{_escape_like(period_contains)}%")
        params.append(int(limit))
        cols = ", ".join(f"f.{c.strip()}" for c in _FACT_COLUMNS.split(","))
        sql = (
            f"SELECT {cols}, d.file_name FROM facts f JOIN documents d ON d.id = f.document_id"
            f" WHERE {' AND '.join(clauses)} ORDER BY f.page_number, f.metric LIMIT %s"
        )
        with tenant_tx(self.tenant_id) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            FactRecord(
                id=str(r["id"]),
                doc_id=str(r["document_id"]),
                document_name=r["file_name"],
                metric=r["metric"],
                value=r["value"],
                value_text=r["value_text"],
                unit=r["unit"],
                period=r["period"],
                page_number=r["page_number"],
                content_hash=r["content_hash"],
                chunk_id=r["chunk_id"],
                source_excerpt=r["source_excerpt"],
                extractor=r["extractor"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PgPageIndexStore(_TenantBound):
    def save(self, index: PageIndex) -> None:
        did = as_uuid(index.doc_id)
        if did is None:
            raise ValueError("PageIndex.doc_id must be a UUID")
        with tenant_tx(self.tenant_id) as conn:
            conn.execute(
                "INSERT INTO page_indexes (document_id, tree) VALUES (%s, %s)"
                " ON CONFLICT (document_id) DO UPDATE SET tree = EXCLUDED.tree",
                (did, Jsonb(index.model_dump(mode="json"))),
            )

    def load(self, doc_id: str) -> PageIndex | None:
        did = as_uuid(doc_id)
        if did is None:
            return None
        with tenant_tx(self.tenant_id) as conn:
            row = conn.execute("SELECT tree FROM page_indexes WHERE document_id = %s", (did,)).fetchone()
        return PageIndex.model_validate(row["tree"]) if row else None


def pg_stores(tenant_id: str | UUID) -> Stores:
    return Stores(
        chunks=PgChunkStore(tenant_id),
        facts=PgFactStore(tenant_id),
        pageindex=PgPageIndexStore(tenant_id),
    )
