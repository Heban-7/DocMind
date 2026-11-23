"""Structured document model and page-level extraction (V2).

Replaces the V1 contract (one Markdown string per document) with a typed model
that keeps every block, table cell and box, plus a per-page quality record.
Markdown is still rendered from the model for the existing chunker.
"""

from src.document.model import (
    BBox,
    Block,
    BlockType,
    DocumentModel,
    Page,
    PageQuality,
    Table,
    TableCell,
)

__all__ = [
    "BBox",
    "Block",
    "BlockType",
    "DocumentModel",
    "Page",
    "PageQuality",
    "Table",
    "TableCell",
]
