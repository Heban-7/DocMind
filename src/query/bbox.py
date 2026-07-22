"""
Page bounding-box resolution for provenance citations.

MVP policy (honest, not decorative):
  * When the source PDF is available, return a *page-level* bbox covering the
    full page surface (real width/height from pdfplumber).
  * When the PDF cannot be opened, return ``BoundingBox.unresolved()`` -- zeros
    with null dimensions -- rather than inventing US-Letter coordinates.
  * Block-level Docling boxes can replace page-level ones later without
    changing the Citation contract.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from src.models.provenance import BoundingBox

logger = logging.getLogger("docmind.provenance")


@lru_cache(maxsize=128)
def _page_size(pdf_path: str, page_number: int) -> tuple[float, float] | None:
    """Return (width, height) in PDF points for a 1-indexed page, or None."""
    path = Path(pdf_path)
    if not path.exists() or page_number < 1:
        return None
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            if page_number > len(pdf.pages):
                return None
            page = pdf.pages[page_number - 1]
            return (float(page.width), float(page.height))
    except Exception as exc:  # pragma: no cover - I/O / parse errors
        logger.warning("Could not read page size from %s p%s: %s", pdf_path, page_number, exc)
        return None


def resolve_page_bbox(
    pdf_path: str | Path | None,
    page_number: int,
) -> BoundingBox:
    """Resolve a page-level bbox from the PDF, or an unresolved placeholder."""
    if pdf_path is None:
        return BoundingBox.unresolved()
    size = _page_size(str(pdf_path), int(page_number))
    if size is None:
        return BoundingBox.unresolved()
    width, height = size
    if width <= 0 or height <= 0:
        return BoundingBox.unresolved()
    return BoundingBox.full_page(width, height)


def clear_page_size_cache() -> None:
    """Test helper: drop cached page dimensions."""
    _page_size.cache_clear()
