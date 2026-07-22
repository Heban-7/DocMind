"""
Assemble a ProvenanceChain from tool evidence hits.

Analogy: the research assistants (tools) hand you sticky notes. This module
staples them into a formal footnote sheet -- document, page, bbox, hash -- that
the Query Agent must attach to every substantive answer.
"""

from __future__ import annotations

from pathlib import Path

from src.models.provenance import Citation, ProvenanceChain
from src.query.bbox import resolve_page_bbox
from src.query.evidence import EvidenceHit, ToolResult


def citation_from_hit(
    hit: EvidenceHit,
    *,
    pdf_path: str | Path | None = None,
) -> Citation:
    """Convert one EvidenceHit into a Citation with a resolved page bbox."""
    bbox = resolve_page_bbox(pdf_path, hit.page_number)
    return Citation(
        document_name=hit.document_name or hit.doc_id or "unknown",
        page_number=hit.page_number,
        bbox=bbox,
        content_hash=hit.content_hash or "",
        chunk_id=hit.chunk_id,
        excerpt=(hit.excerpt or hit.title or "")[:500],
    )


def _dedupe_key(citation: Citation) -> tuple:
    return (
        citation.document_name,
        citation.page_number,
        citation.content_hash,
        citation.excerpt[:120],
    )


def assemble_provenance(
    evidence: list[EvidenceHit] | list[ToolResult],
    *,
    pdf_path: str | Path | None = None,
    max_citations: int = 8,
) -> ProvenanceChain:
    """Build an ordered, deduplicated ProvenanceChain from tool evidence.

    Accepts either a flat list of ``EvidenceHit`` or a list of ``ToolResult``
    (hits are concatenated in order). Empty input -> empty chain.
    """
    hits: list[EvidenceHit] = []
    for item in evidence:
        if isinstance(item, ToolResult):
            hits.extend(item.hits)
        else:
            hits.append(item)

    citations: list[Citation] = []
    seen: set[tuple] = set()
    for hit in hits:
        citation = citation_from_hit(hit, pdf_path=pdf_path)
        key = _dedupe_key(citation)
        if key in seen:
            continue
        # Prefer hits that carry a real content hash when deduping near-duplicates
        # already handled by key; still skip empty-echo citations with no text.
        if not citation.excerpt and not citation.content_hash:
            continue
        seen.add(key)
        citations.append(citation)
        if len(citations) >= max_citations:
            break

    return ProvenanceChain(citations=citations)
