"""
The three Query Agent tools (Phase 4 Step 5).

Each function is a thin, testable wrapper over PageIndex / Chroma / FactTable.
They return ``ToolResult`` evidence bundles -- never free-form answers.

  1. pageindex_navigate  -- which sections look relevant?
  2. semantic_search     -- which LDUs match by meaning?
  3. structured_query    -- which FactTable rows match filters / SQL?
"""

from __future__ import annotations

from pathlib import Path

from src.config import PAGEINDEX_DIR
from src.facts.models import FactRecord
from src.facts.store import FactStore
from src.models.page_index import PageIndex
from src.models.query import ToolName, ToolTrace
from src.pageindex.builder import load_page_index
from src.pageindex.navigate import navigate
from src.query.evidence import EvidenceHit, ToolResult
from src.retrieval.embeddings import EmbeddingClient
from src.retrieval.ingest import semantic_search as chroma_semantic_search
from src.retrieval.vector_store import ChromaLDUStore, RetrievedChunk


def pageindex_navigate(
    topic: str,
    *,
    doc_id: str,
    top_k: int = 5,
    index: PageIndex | None = None,
    pageindex_dir: Path | None = None,
) -> ToolResult:
    """Traverse the PageIndex tree and return the top-K matching sections."""
    topic = (topic or "").strip()
    args = {"topic": topic, "doc_id": doc_id, "top_k": top_k}

    if not topic:
        trace = ToolTrace(
            tool=ToolName.PAGEINDEX_NAVIGATE,
            arguments=args,
            summary="empty topic; no sections returned",
        )
        return ToolResult(tool=ToolName.PAGEINDEX_NAVIGATE, hits=[], trace=trace)

    idx = index or load_page_index(doc_id, directory=pageindex_dir or PAGEINDEX_DIR)
    ranked = navigate(idx, topic, top_k=top_k)

    hits: list[EvidenceHit] = []
    for node, score in ranked:
        # Prefer a chunk hash from the section when available (provenance hook).
        content_hash = ""
        chunk_id = node.chunk_ids[0] if node.chunk_ids else None
        excerpt = node.summary or f"Section '{node.title}' (pp. {node.page_start}-{node.page_end})"
        hits.append(
            EvidenceHit(
                tool=ToolName.PAGEINDEX_NAVIGATE,
                document_name=idx.source_filename or doc_id,
                doc_id=doc_id,
                page_number=node.page_start,
                content_hash=content_hash,
                chunk_id=chunk_id,
                excerpt=excerpt[:400],
                title=node.title,
                score=float(score),
                extra={
                    "path": list(node.path),
                    "page_start": node.page_start,
                    "page_end": node.page_end,
                    "data_types": list(node.data_types_present),
                    "chunk_ids": list(node.chunk_ids),
                },
            )
        )

    trace = ToolTrace(
        tool=ToolName.PAGEINDEX_NAVIGATE,
        arguments=args,
        summary=f"{len(hits)} section(s); top={hits[0].title if hits else '-'}",
    )
    return ToolResult(tool=ToolName.PAGEINDEX_NAVIGATE, hits=hits, trace=trace)


def _hit_from_retrieved(chunk: RetrievedChunk) -> EvidenceHit:
    from src.config import EVIDENCE_EXCERPT_CHARS

    page = chunk.page_numbers[0] if chunk.page_numbers else 1
    excerpt_n = max(200, int(EVIDENCE_EXCERPT_CHARS))
    return EvidenceHit(
        tool=ToolName.SEMANTIC_SEARCH,
        document_name=chunk.document_name,
        doc_id=chunk.doc_id,
        page_number=page,
        content_hash=chunk.content_hash,
        chunk_id=chunk.chunk_id,
        excerpt=chunk.text[:excerpt_n],
        title=" > ".join(chunk.parent_hierarchy) if chunk.parent_hierarchy else "",
        score=float(chunk.score),
        extra={
            "page_numbers": list(chunk.page_numbers),
            "parent_hierarchy": list(chunk.parent_hierarchy),
            "chunk_type": chunk.chunk_type,
            "distance": chunk.distance,
        },
    )


def tool_semantic_search(
    query: str,
    *,
    doc_id: str | None = None,
    top_k: int = 7,
    store: ChromaLDUStore | None = None,
    embedder: EmbeddingClient | None = None,
) -> ToolResult:
    """Embed ``query`` and return the nearest LDUs from Chroma."""
    query = (query or "").strip()
    args = {"query": query, "doc_id": doc_id, "top_k": top_k}

    if not query:
        trace = ToolTrace(
            tool=ToolName.SEMANTIC_SEARCH,
            arguments=args,
            summary="empty query; no hits",
        )
        return ToolResult(tool=ToolName.SEMANTIC_SEARCH, hits=[], trace=trace)

    retrieved = chroma_semantic_search(
        query, doc_id=doc_id, top_k=top_k, store=store, embedder=embedder
    )
    hits = [_hit_from_retrieved(r) for r in retrieved]
    trace = ToolTrace(
        tool=ToolName.SEMANTIC_SEARCH,
        arguments=args,
        summary=f"{len(hits)} LDU hit(s)",
    )
    return ToolResult(tool=ToolName.SEMANTIC_SEARCH, hits=hits, trace=trace)


def _hit_from_fact(fact: FactRecord) -> EvidenceHit:
    label = fact.metric
    if fact.period:
        label = f"{fact.metric} ({fact.period})"
    excerpt = (
        f"{fact.metric} = {fact.value_text}"
        + (f" {fact.unit}" if fact.unit and fact.unit not in fact.value_text else "")
        + (f" [{fact.period}]" if fact.period else "")
    )
    return EvidenceHit(
        tool=ToolName.STRUCTURED_QUERY,
        document_name=fact.document_name,
        doc_id=fact.doc_id,
        page_number=fact.page_number,
        content_hash=fact.content_hash,
        chunk_id=fact.chunk_id or None,
        excerpt=(fact.source_excerpt or excerpt)[:400],
        title=label,
        score=1.0,
        extra={
            "metric": fact.metric,
            "value": fact.value,
            "value_text": fact.value_text,
            "unit": fact.unit,
            "period": fact.period,
            "fact_id": fact.id,
        },
    )


def structured_query(
    *,
    doc_id: str | None = None,
    metric_contains: str | None = None,
    period_contains: str | None = None,
    sql: str | None = None,
    limit: int = 20,
    store: FactStore | None = None,
) -> ToolResult:
    """Query the FactTable via safe filters or a read-only SELECT.

    Prefer ``metric_contains`` / ``period_contains`` for agent use. Pass ``sql``
    only for explicit SELECT power queries (still blocked from writes).
    """
    args = {
        "doc_id": doc_id,
        "metric_contains": metric_contains,
        "period_contains": period_contains,
        "sql": sql,
        "limit": limit,
    }
    store = store or FactStore()

    hits: list[EvidenceHit] = []
    if sql and sql.strip():
        rows = store.select(sql)
        # Map raw SQL dict rows into EvidenceHits when columns match schema.
        for row in rows[:limit]:
            fact = FactRecord(
                id=str(row.get("id") or ""),
                doc_id=str(row.get("doc_id") or doc_id or ""),
                document_name=str(row.get("document_name") or ""),
                metric=str(row.get("metric") or ""),
                value=row.get("value"),
                value_text=str(row.get("value_text") or row.get("value") or ""),
                unit=str(row.get("unit") or ""),
                period=str(row.get("period") or ""),
                page_number=int(row.get("page_number") or 1),
                content_hash=str(row.get("content_hash") or ""),
                chunk_id=str(row.get("chunk_id") or ""),
                source_excerpt=str(row.get("source_excerpt") or ""),
            )
            if fact.metric or fact.value_text:
                hits.append(_hit_from_fact(fact))
        summary = f"sql returned {len(hits)} row(s)"
    else:
        facts = store.search(
            doc_id=doc_id,
            metric_contains=metric_contains,
            period_contains=period_contains,
            limit=limit,
        )
        hits = [_hit_from_fact(f) for f in facts]
        summary = f"{len(hits)} fact row(s)"

    trace = ToolTrace(
        tool=ToolName.STRUCTURED_QUERY, arguments=args, summary=summary
    )
    return ToolResult(tool=ToolName.STRUCTURED_QUERY, hits=hits, trace=trace)


# Public alias matching the docs' tool name for semantic search.
semantic_search = tool_semantic_search
