"""
Assemble a ProvenanceChain from tool evidence hits.

Analogy: the research assistants (tools) hand you sticky notes. This module
staples them into a formal footnote sheet -- document, page, bbox, hash -- that
the Query Agent must attach to every substantive answer.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.models.provenance import BoundingBox, Citation, ProvenanceChain
from src.query.bbox import resolve_page_bbox
from src.query.evidence import EvidenceHit, ToolResult
from src.query.page_map import resolve_printed_page


def citation_from_hit(
    hit: EvidenceHit,
    *,
    pdf_path: str | Path | None = None,
) -> Citation:
    """Convert one EvidenceHit into a Citation with the box that prints it.

    ``page_number`` stays physical. ``printed_page`` is taken from the hit when
    already set, otherwise resolved from the PDF ``/PageLabels`` map (optional).

    The box, best first: the table cell a fact was read from; the cell (and
    its row label) or text block that prints the numbers the answer states,
    found in the document model beside the PDF; the blocks the passage came
    from; the whole page.
    """
    from src.query.locate import locate_on_pages, model_beside, union

    page_number = hit.page_number
    bbox = resolve_page_bbox(pdf_path, page_number)
    boxes: list[BoundingBox] = []
    kind = "page"
    extra = hit.extra or {}
    cells = [c for c in (extra.get("bboxes") or [extra.get("bbox")]) if c and len(c) == 4]
    if cells and bbox.page_height:
        # A fact knows its cell: [x0, top, x1, bottom] from the top-left corner.
        boxes = [
            BoundingBox(
                x0=float(x0), y0=bbox.page_height - float(bottom), x1=float(x1), y1=bbox.page_height - float(top),
                page_width=bbox.page_width, page_height=bbox.page_height,
            )
            for x0, top, x1, bottom in cells
        ]
        bbox, kind = union(boxes), "fact"
    elif pdf_path is not None:
        pages = [hit.page_number] + [int(p) for p in (extra.get("page_numbers") or []) if isinstance(p, int)]
        page_number, found, kind = locate_on_pages(
            model_beside(pdf_path),
            pages,
            numbers=list(extra.get("claim_numbers") or []),
            context=str(extra.get("claim_text") or ""),
            excerpt=hit.excerpt or "",
        )
        if found:
            boxes, bbox = found, union(found)
    printed = hit.printed_page if page_number == hit.page_number else None
    if printed is None and pdf_path is not None:
        printed = resolve_printed_page(pdf_path, page_number)
    return Citation(
        document_name=hit.document_name or hit.doc_id or "unknown",
        doc_id=hit.doc_id or None,
        page_number=page_number,
        bbox=bbox,
        boxes=boxes,
        box_kind=kind,
        content_hash=hit.content_hash or "",
        chunk_id=hit.chunk_id,
        excerpt=(hit.excerpt or hit.title or "")[:700],
        printed_page=printed,
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
    pdf_for: Callable[[str], str | Path | None] | None = None,
) -> ProvenanceChain:
    """Build an ordered, deduplicated ProvenanceChain from tool evidence.

    Accepts either a flat list of ``EvidenceHit`` or a list of ``ToolResult``
    (hits are concatenated in order). Empty input -> empty chain.
    ``pdf_for`` maps a hit's document id to its PDF, so an answer that cites
    two documents boxes each on its own file; ``pdf_path`` is the fallback.
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
        citation = citation_from_hit(hit, pdf_path=_pdf(hit, pdf_path, pdf_for))
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


def _pdf(hit: EvidenceHit, default, pdf_for):
    if pdf_for is not None and hit.doc_id:
        try:
            found = pdf_for(hit.doc_id)
        except Exception:  # a missing file only costs page labels and boxes
            found = None
        # another document's PDF would give a box on the wrong file
        return found
    return default
