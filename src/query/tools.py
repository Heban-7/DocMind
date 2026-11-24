"""
The three Query Agent tools (Phase 4 Step 5).

Each function is a thin, testable wrapper over the PageIndex, chunk and fact
stores. They return ``ToolResult`` evidence bundles -- never free-form answers.

  1. pageindex_navigate  -- which sections look relevant?
  2. semantic_search     -- which LDUs match by meaning?
  3. structured_query    -- which FactTable rows match the filters?
"""

from __future__ import annotations

from src.facts.models import FactRecord
from src.models.page_index import PageIndex
from src.models.query import ToolName, ToolTrace
from src.pageindex.navigate import navigate
from src.query.evidence import EvidenceHit, ToolResult
from src.retrieval.embeddings import EmbeddingClient
from src.retrieval.ingest import semantic_search as store_semantic_search
from src.stores.base import ChunkStore, FactStore, PageIndexStore, RetrievedChunk


def pageindex_navigate(
    topic: str,
    *,
    doc_id: str,
    top_k: int = 5,
    index: PageIndex | None = None,
    store: PageIndexStore | None = None,
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

    idx = index or (store.load(doc_id) if store is not None else None)
    if idx is None:
        trace = ToolTrace(
            tool=ToolName.PAGEINDEX_NAVIGATE,
            arguments=args,
            summary="no page index for this document",
        )
        return ToolResult(tool=ToolName.PAGEINDEX_NAVIGATE, hits=[], trace=trace)
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
    store: ChunkStore,
    embedder: EmbeddingClient | None = None,
) -> ToolResult:
    """Embed ``query`` and return the nearest LDUs from the chunk store."""
    query = (query or "").strip()
    args = {"query": query, "doc_id": doc_id, "top_k": top_k}

    if not query:
        trace = ToolTrace(
            tool=ToolName.SEMANTIC_SEARCH,
            arguments=args,
            summary="empty query; no hits",
        )
        return ToolResult(tool=ToolName.SEMANTIC_SEARCH, hits=[], trace=trace)

    retrieved = store_semantic_search(
        query, doc_id=doc_id, top_k=top_k, store=store, embedder=embedder
    )
    hits = [_hit_from_retrieved(r) for r in retrieved]
    trace = ToolTrace(
        tool=ToolName.SEMANTIC_SEARCH,
        arguments=args,
        summary=f"{len(hits)} LDU hit(s)",
    )
    return ToolResult(tool=ToolName.SEMANTIC_SEARCH, hits=hits, trace=trace)


def _scale_word(scale: float) -> str:
    return {1e3: " thousand", 1e6: " million", 1e9: " billion", 1e12: " trillion"}.get(scale, "" if scale == 1 else f" x{scale:g}")


def _fact_text(fact: FactRecord) -> str:
    """'Total revenue | 2023/24 | 1,234 (ETB million)'"""
    unit = fact.unit if fact.unit == "%" else f"{fact.currency or fact.unit}{_scale_word(fact.scale)}".strip()
    parts = [p for p in (fact.row_group, fact.row_label or fact.metric, fact.column_label) if p]
    head = " / ".join(dict.fromkeys(parts)) or fact.metric
    return f"{head} = {fact.value_text}" + (f" ({unit})" if unit and unit not in fact.value_text else "") + (
        f" [{fact.table_title}]" if fact.table_title else ""
    )


def _hit_from_fact(fact: FactRecord, score: float = 1.0) -> EvidenceHit:
    return EvidenceHit(
        tool=ToolName.STRUCTURED_QUERY,
        document_name=fact.document_name,
        doc_id=fact.doc_id,
        page_number=fact.page_number,
        content_hash=fact.content_hash,
        chunk_id=fact.chunk_id or None,
        excerpt=_fact_text(fact)[:400],
        title=fact.row_label or fact.metric,
        score=score,
        extra={
            "metric": fact.metric,
            "value": fact.value,
            "value_text": fact.value_text,
            "scale": fact.scale,
            "value_abs": fact.absolute_value,
            "unit": fact.unit,
            "period": fact.period,
            "column": fact.column_label,
            "table_id": fact.table_id,
            "bbox": fact.bbox,  # top-left origin; citations convert it
            "fact_id": fact.id,
        },
    )


def _format_value(value: float, unit: str) -> str:
    if unit == "%":
        return f"{value:+.2f}%"
    if abs(value) >= 1000:
        return f"{value:,.0f}" + (f" {unit}" if unit else "")
    return f"{value:,.4g}" + (f" {unit}" if unit else "")


def _hit_from_computed(result, computed, index: int) -> EvidenceHit:
    from src.facts.query import CHANGE_OPS

    spec = result.spec
    inputs = [f for f in result.facts if f.id in computed.inputs]
    anchor = inputs[-1] if inputs else (result.facts[0] if result.facts else None)
    if spec.op in CHANGE_OPS and len(inputs) == 2:
        a, b = inputs
        what = f"{spec.op.replace('_', ' ')} of '{a.row_label or a.metric}' from {spec.periods[0]} ({_fact_text(a).split(' = ')[-1]}) to {spec.periods[1]} ({_fact_text(b).split(' = ')[-1]})"
    else:
        what = f"{computed.formula} of '{spec.metric}' over {len(inputs)} cell(s)"
    excerpt = f"COMPUTED BY THE DATABASE from the cited cells: {what} = {_format_value(computed.value, computed.unit)}"
    return EvidenceHit(
        tool=ToolName.STRUCTURED_QUERY,
        document_name=anchor.document_name if anchor else "",
        doc_id=anchor.doc_id if anchor else "",
        page_number=anchor.page_number if anchor else 1,
        content_hash=anchor.content_hash if anchor else "",
        excerpt=excerpt[:500],
        title=f"{spec.op}: {spec.metric}",
        score=2.0 - 0.01 * index,
        extra={
            "computed": True,
            "op": spec.op,
            "value": computed.value,
            "unit": computed.unit,
            "formula": computed.formula,
            "inputs": list(computed.inputs),
            "bbox": anchor.bbox if anchor else None,
        },
    )


def structured_query(
    *,
    store: FactStore,
    doc_id: str | None = None,
    spec: dict | None = None,
    metric_contains: str | None = None,
    period_contains: str | None = None,
    limit: int = 20,
) -> ToolResult:
    """Ask the FactTable a checked question; computations come from the database.

    ``spec`` is a FactQuery as JSON: ``{"op": "percent_change", "metric":
    "total revenue", "periods": ["2022/23", "2023/24"]}``. The older
    ``metric_contains`` / ``period_contains`` filters still work and mean a
    lookup. There is no way to send SQL.
    """
    from pydantic import ValidationError

    from src.facts.query import FactQuery

    raw = dict(spec or {})
    if not raw and metric_contains:
        raw = {"op": "lookup", "metric": metric_contains, "periods": [period_contains] if period_contains else [], "limit": limit}
    args = {"doc_id": doc_id, **raw}
    try:
        query = FactQuery.model_validate(raw)
    except ValidationError as exc:
        trace = ToolTrace(tool=ToolName.STRUCTURED_QUERY, arguments=args, summary=f"rejected spec: {exc.errors()[0]['msg']}")
        return ToolResult(tool=ToolName.STRUCTURED_QUERY, hits=[], trace=trace)

    result = store.run_query(query, doc_id=doc_id)
    hits = [_hit_from_computed(result, c, i) for i, c in enumerate(result.computed)]
    hits += [_hit_from_fact(f, score=1.0 - 0.01 * i) for i, f in enumerate(result.facts)]
    summary = f"{query.op}: {len(result.facts)} fact(s)" + (f", {len(result.computed)} computed" if result.computed else "")
    trace = ToolTrace(tool=ToolName.STRUCTURED_QUERY, arguments={"doc_id": doc_id, **query.model_dump()}, summary=summary)
    return ToolResult(tool=ToolName.STRUCTURED_QUERY, hits=hits, trace=trace)


# Public alias matching the docs' tool name for semantic search.
semantic_search = tool_semantic_search
