"""
Strategy B (Docling variant) -- Layout-Aware via IBM Docling.

Lightweight (CPU-friendly), state-of-the-art tables (TableFormer), excellent for
enterprise layouts. The selector picks this by default for Strategy B.
"""

from __future__ import annotations

from src.config import EXTRACTION_MAX_PAGES
from src.extraction._docling_support import convert_to_markdown
from src.extraction.base import BaseExtractionEngine


class DoclingLayoutEngine(BaseExtractionEngine):
    """Reconstruct document structure into Markdown using Docling."""

    name = "layout_docling"

    def __init__(self, max_pages: int | None = EXTRACTION_MAX_PAGES):
        self.max_pages = max_pages

    def extract(self, file_path: str) -> str:
        return convert_to_markdown(
            file_path, do_ocr=False, max_pages=self.max_pages
        )
