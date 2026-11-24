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

    def replace_doc_chunks(
        self, doc_id, chunks: list[DocumentChunk], embeddings, *, document_name: str = "", contexts=None, embed_hashes=None
    ) -> int:
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
                contexts[i] if contexts else "",
                embed_hashes[i] if embed_hashes else c.metadata.content_hash,
            )
            for i, c in enumerate(chunks)
        ]
        with tenant_tx(self.tenant_id) as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (did,))
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunks (id, document_id, ordinal, text, chunk_type, section_path, page_numbers,"
                    " content_hash, word_count, embedding, context, embed_hash)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )
        return len(rows)

    def existing_embeddings(self, doc_id: str) -> dict[str, list[float]]:
        """Vectors already stored for this document, by the hash of the exact text embedded."""
        did = as_uuid(doc_id)
        if did is None:
            return {}
        with tenant_tx(self.tenant_id) as conn:
            rows = conn.execute(
                "SELECT DISTINCT ON (embed_hash) embed_hash, embedding FROM chunks"
                " WHERE document_id = %s AND embedding IS NOT NULL AND embed_hash <> ''",
                (did,),
            ).fetchall()
        out: dict[str, list[float]] = {}
        for r in rows:
            v = r["embedding"]  # a pgvector Vector, or a numpy array, depending on the adapter
            out[r["embed_hash"]] = [float(x) for x in (v.to_list() if hasattr(v, "to_list") else v)]
        return out

    def search(self, query_text: str, query_embedding, *, doc_id: str | None = None, top_k: int = 20) -> list[RetrievedChunk]:
        """Hybrid search: vector and keyword rankings fused with reciprocal rank fusion (k = 60)."""
        from src.retrieval.keywords import keyword_query, quoted_phrases

        did = as_uuid(doc_id) if doc_id else None
        if doc_id and did is None:
            return []
        tsq = keyword_query(query_text)
        phrases = quoted_phrases(query_text)
        params = {
            "ph": phrases or "nothing_to_match",
            "has_p": bool(phrases),
            "v": _vec(query_embedding) if query_embedding is not None else None,
            "has_v": query_embedding is not None,
            "tsq": tsq or "nothing_to_match",
            "has_t": bool(tsq),
            "doc": did,
            "n": 40,
            "k": int(top_k),
        }
        sql = """
            WITH vec AS (
                SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> %(v)s::vector) AS r
                  FROM chunks c JOIN documents d ON d.id = c.document_id
                 WHERE %(has_v)s AND d.searchable AND c.embedding IS NOT NULL
                   AND (%(doc)s::uuid IS NULL OR c.document_id = %(doc)s::uuid)
                 ORDER BY c.embedding <=> %(v)s::vector LIMIT %(n)s
            ), kw AS (
                SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q) DESC) AS r
                  FROM chunks c JOIN documents d ON d.id = c.document_id,
                       to_tsquery('english', %(tsq)s) q
                 WHERE %(has_t)s AND d.searchable AND c.tsv @@ q
                   AND (%(doc)s::uuid IS NULL OR c.document_id = %(doc)s::uuid)
                 ORDER BY ts_rank_cd(c.tsv, q) DESC LIMIT %(n)s
            ), ph AS (
                -- a label the question quotes ("Government Bond") is a third vote
                SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q) DESC) AS r
                  FROM chunks c JOIN documents d ON d.id = c.document_id,
                       to_tsquery('english', %(ph)s) q
                 WHERE %(has_p)s AND d.searchable AND c.tsv @@ q
                   AND (%(doc)s::uuid IS NULL OR c.document_id = %(doc)s::uuid)
                 ORDER BY ts_rank_cd(c.tsv, q) DESC LIMIT %(n)s
            ), fused AS (
                SELECT id, sum(1.0 / (60 + r)) AS score
                  FROM (SELECT * FROM vec UNION ALL SELECT * FROM kw UNION ALL SELECT * FROM ph) x GROUP BY id
            )
            SELECT c.id, c.text, c.context, c.document_id, d.file_name, c.page_numbers, c.section_path, c.content_hash,
                   c.chunk_type, f.score,
                   CASE WHEN %(has_v)s AND c.embedding IS NOT NULL THEN c.embedding <=> %(v)s::vector ELSE 1.0 END AS distance
              FROM fused f JOIN chunks c ON c.id = f.id JOIN documents d ON d.id = c.document_id
             ORDER BY f.score DESC, c.ordinal
             LIMIT %(k)s
        """
        with tenant_tx(self.tenant_id) as conn:
            conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            rows = conn.execute(sql, params).fetchall()  # keyword_query only emits words, phrases and |
        return [
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
                context=r["context"],
                relevance=round(min(1.0, float(r["score"]) * 20.3), 4),
            )
            for r in rows
        ]

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


_FACT_FIELDS = (
    "id", "document_id", "metric", "value", "value_text", "unit", "period", "page_number", "content_hash",
    "chunk_id", "source_excerpt", "extractor", "created_at", "row_label", "row_group", "column_label",
    "table_title", "scale", "currency", "table_id", "row_index", "col_index", "bbox", "source", "confidence",
    "period_key",
)
_FACT_COLUMNS = ", ".join(_FACT_FIELDS)
_SELECT_FACT = ", ".join(f"f.{c}" for c in _FACT_FIELDS) + ", d.file_name"


def _fact_from_row(r: dict, prefix: str = "") -> FactRecord:
    g = lambda k: r[prefix + k]  # noqa: E731
    return FactRecord(
        id=str(g("id")),
        doc_id=str(g("document_id")),
        document_name=g("file_name"),
        metric=g("metric"),
        value=g("value"),
        value_text=g("value_text"),
        unit=g("unit"),
        period=g("period"),
        page_number=g("page_number"),
        content_hash=g("content_hash"),
        chunk_id=g("chunk_id"),
        source_excerpt=g("source_excerpt"),
        extractor=g("extractor"),
        created_at=g("created_at"),
        row_label=g("row_label"),
        row_group=g("row_group"),
        column_label=g("column_label"),
        table_title=g("table_title"),
        scale=g("scale"),
        currency=g("currency"),
        table_id=g("table_id"),
        row_index=g("row_index"),
        col_index=g("col_index"),
        bbox=list(g("bbox")) if g("bbox") is not None else None,
        source=g("source"),
        confidence=g("confidence"),
        period_key=g("period_key"),
    )


class PgFactStore(_TenantBound):
    def replace_doc_facts(self, doc_id: str, facts: list[FactRecord]) -> int:
        did = as_uuid(doc_id)
        if did is None:
            raise ValueError("doc_id must be a UUID")
        rows = [
            (
                f.id, did, f.metric, f.value, f.value_text, f.unit, f.period, f.page_number, f.content_hash,
                f.chunk_id, f.source_excerpt, f.extractor, f.created_at, f.row_label, f.row_group, f.column_label,
                f.table_title, f.scale, f.currency, f.table_id, f.row_index, f.col_index, f.bbox,
                f.source if f.source in ("table", "text") else "text", f.confidence, f.period_key,
            )
            for f in facts
        ]
        placeholders = ", ".join(["%s"] * len(_FACT_FIELDS))
        with tenant_tx(self.tenant_id) as conn:
            conn.execute("DELETE FROM facts WHERE document_id = %s", (did,))
            with conn.cursor() as cur:
                cur.executemany(f"INSERT INTO facts ({_FACT_COLUMNS}) VALUES ({placeholders})", rows)
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
            clauses.append("f.search_text ILIKE %s")
            params.append(f"%{_escape_like(metric_contains.lower())}%")
        if period_contains:
            clauses.append("(f.period ILIKE %s OR f.column_label ILIKE %s)")
            params += [f"%{_escape_like(period_contains)}%"] * 2
        params.append(int(limit))
        sql = (
            f"SELECT {_SELECT_FACT} FROM facts f JOIN documents d ON d.id = f.document_id"
            f" WHERE {' AND '.join(clauses)} ORDER BY f.page_number, f.metric LIMIT %s"
        )
        with tenant_tx(self.tenant_id) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_fact_from_row(r) for r in rows]

    # --- numeric questions -------------------------------------------------------

    def run_query(self, spec, *, doc_id: str | None = None):
        """Compile a checked FactQuery to fixed SQL and run it read-only.

        Runs as docmind_reader (SELECT on facts and documents only), inside
        the tenant's row-level security, with a 3-second limit. Every user
        value is a bind parameter; the SQL text comes only from this method.
        """
        from src.facts.query import CHANGE_OPS, COLUMN_OPS, Computed, FactQueryResult
        from src.facts.typed import normalize_period

        did = as_uuid(doc_id) if doc_id else None
        if doc_id and did is None:
            return FactQueryResult(spec, [])
        base = {"m": spec.metric.lower(), "doc": did, "unit": spec.unit, "col": f"%{_escape_like(spec.column or '')}%"}
        candidates = f"""
            SELECT {_SELECT_FACT}, f.value_abs, word_similarity(%(m)s, f.search_text) AS ws
              FROM facts f JOIN documents d ON d.id = f.document_id
             WHERE d.searchable AND f.value IS NOT NULL
               AND %(m)s <%% f.search_text
               AND (%(doc)s::uuid IS NULL OR f.document_id = %(doc)s::uuid)
               AND (%(unit)s::text IS NULL OR f.unit = %(unit)s::text)
               AND f.column_label ILIKE %(col)s
        """

        def period_clause(alias: str, i: int, params: dict, period: str) -> str:
            params[f"pk{i}"] = normalize_period(period)
            params[f"pl{i}"] = f"%{_escape_like(period)}%"
            return f"(({alias}.period_key <> '' AND {alias}.period_key = %(pk{i})s) OR {alias}.column_label ILIKE %(pl{i})s)"

        with tenant_tx(self.tenant_id) as conn:
            conn.execute("SET LOCAL ROLE docmind_reader")
            conn.execute("SET LOCAL statement_timeout = '3s'")
            conn.execute("SET LOCAL pg_trgm.word_similarity_threshold = 0.45")
            if spec.op in CHANGE_OPS:
                params = dict(base)
                a_clause = period_clause("c", 0, params, spec.periods[0])
                b_clause = period_clause("c", 1, params, spec.periods[1])
                rows = conn.execute(
                    f"""
                    WITH c AS ({candidates}),
                         a AS (SELECT * FROM c WHERE {a_clause}),
                         b AS (SELECT * FROM c WHERE {b_clause})
                    SELECT {", ".join(f"a.{k} AS a_{k}" for k in (*_FACT_FIELDS, "file_name", "value_abs", "ws"))},
                           {", ".join(f"b.{k} AS b_{k}" for k in (*_FACT_FIELDS, "file_name", "value_abs", "ws"))},
                           b.value_abs - a.value_abs AS difference,
                           CASE WHEN a.value_abs <> 0
                                THEN (b.value_abs - a.value_abs) / abs(a.value_abs) * 100 END AS percent_change
                      FROM a JOIN b ON a.document_id = b.document_id AND a.id <> b.id AND a.unit = b.unit
                       AND ((a.table_id <> '' AND a.table_id = b.table_id AND a.row_index = b.row_index)
                            OR a.metric = b.metric)
                     ORDER BY a.ws + b.ws DESC, a.confidence + b.confidence DESC
                     LIMIT 3
                    """,
                    params,
                ).fetchall()
                out = FactQueryResult(spec, [])
                for r in rows:
                    a, b = _fact_from_row(r, "a_"), _fact_from_row(r, "b_")
                    value = r[spec.op]
                    if value is None:
                        continue
                    p1, p2 = spec.periods
                    formula = f"{p2} - {p1}" if spec.op == "difference" else f"({p2} - {p1}) / |{p1}| x 100"
                    out.facts += [a, b]
                    out.computed.append(
                        Computed(round(float(value), 4), "%" if spec.op == "percent_change" else a.unit, formula, [a.id, b.id])
                    )
                return out

            params = dict(base)
            where = ""
            if spec.periods:
                where = "WHERE " + " OR ".join(period_clause("c", i, params, p) for i, p in enumerate(spec.periods))
            params["limit"] = spec.limit
            ranked = conn.execute(
                f"WITH c AS ({candidates}) SELECT * FROM c {where}"
                " ORDER BY ws DESC, confidence DESC, page_number LIMIT %(limit)s",
                params,
            ).fetchall()
            facts = [_fact_from_row(r) for r in ranked]
            if spec.op not in COLUMN_OPS or not ranked:
                return FactQueryResult(spec, facts)

            # Aggregates run over the best match's table column, without its total rows.
            best = ranked[0]
            agg = {"sum": "sum", "average": "avg", "max": "max", "min": "min", "count": "count"}[spec.op]
            params.update(doc_best=best["document_id"], table=best["table_id"], coli=best["col_index"])
            column_rows = conn.execute(
                f"""
                SELECT {_SELECT_FACT}, f.value_abs FROM facts f JOIN documents d ON d.id = f.document_id
                 WHERE f.document_id = %(doc_best)s AND f.table_id = %(table)s AND f.table_id <> ''
                   AND f.col_index = %(coli)s AND f.value IS NOT NULL AND f.row_label NOT ILIKE '%%total%%'
                 ORDER BY f.row_index LIMIT 50
                """,
                params,
            ).fetchall() or [best]
            value = conn.execute(
                f"SELECT {agg}(v) AS v FROM unnest(%(vals)s::double precision[]) AS v",
                {"vals": [r["value_abs"] for r in column_rows]},
            ).fetchone()["v"]
            column = [_fact_from_row(r) for r in column_rows]
            unit = "rows" if spec.op == "count" else column[0].unit
            inputs = [f.id for f in column]
            label = f"{spec.op} of the column"
            if spec.op in ("max", "min"):
                pick = next((f for f, r in zip(column, column_rows) if r["value_abs"] == value), column[0])
                inputs, label = [pick.id], f"{spec.op} of the column: {pick.row_label}"
            return FactQueryResult(spec, column, [Computed(round(float(value), 4), unit, label, inputs)])


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
