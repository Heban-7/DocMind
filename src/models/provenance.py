"""
Provenance contracts for Phase 4 (Query Agent & Audit Mode).

Every answer the agent produces must be able to point back to evidence in the
source PDF. These models are that fingerprint: document name, page, bounding
box, and content hash -- frozen so a citation cannot silently drift after it is
issued.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BoundingBox(BaseModel):
    """Axis-aligned rectangle on a PDF page (PDF points, origin bottom-left).

    MVP: page-level boxes (full page width/height) are acceptable when block-
    level geometry is not available from Markdown LDUs. Later enrichment can
    replace these with Docling/pdfplumber block boxes without changing callers.
    """

    model_config = ConfigDict(frozen=True)

    x0: float = Field(description="left edge")
    y0: float = Field(description="bottom edge")
    x1: float = Field(description="right edge")
    y1: float = Field(description="top edge")
    page_width: float | None = Field(
        default=None, description="page width in points (optional context)"
    )
    page_height: float | None = Field(
        default=None, description="page height in points (optional context)"
    )

    @classmethod
    def full_page(cls, width: float, height: float) -> BoundingBox:
        """Page-level bbox covering the entire page surface."""
        return cls(
            x0=0.0, y0=0.0, x1=width, y1=height,
            page_width=width, page_height=height,
        )

    @classmethod
    def unresolved(cls) -> BoundingBox:
        """Honest placeholder when page geometry could not be read.

        Uses a degenerate box (all zeros, null page size) so we never invent
        fake US-Letter dimensions. Callers / UIs should treat this as
        "page known, coordinates not yet resolved."
        """
        return cls(x0=0.0, y0=0.0, x1=0.0, y1=0.0, page_width=None, page_height=None)

    @property
    def is_resolved(self) -> bool:
        return self.page_width is not None and self.page_height is not None and self.x1 > 0


class Citation(BaseModel):
    """One auditable pointer from an answer claim back into a source document."""

    model_config = ConfigDict(frozen=True)

    document_name: str = Field(description="source PDF filename")
    page_number: int = Field(ge=1, description="1-indexed physical page")
    bbox: BoundingBox
    content_hash: str = Field(description="SHA-256 of the supporting LDU text")
    chunk_id: str | None = Field(
        default=None, description="LDU id when the hit came from a chunk"
    )
    excerpt: str = Field(
        default="",
        description="short supporting quote shown to the user / auditor",
    )


class ProvenanceChain(BaseModel):
    """Ordered list of citations that together justify an answer or audit verdict.

    An empty chain is allowed only for explicitly unverifiable audit results;
    QueryAnswer validation should prefer at least one citation when answering.
    """

    model_config = ConfigDict(frozen=True)

    citations: list[Citation] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.citations)

    @property
    def is_empty(self) -> bool:
        return len(self.citations) == 0
