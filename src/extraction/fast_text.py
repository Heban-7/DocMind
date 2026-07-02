"""
Strategy A -- Fast Text (Cost: Low).

The cheapest, fastest tier. It simply reads the embedded text layer of a
native-digital PDF with pdfplumber. No AI, no layout reconstruction -- just a
lightning-fast scrape that is "good enough" for clean, single-column digital
documents.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from src.extraction.base import BaseExtractionEngine


class FastTextEngine(BaseExtractionEngine):
    """Pull clean text out of a native-digital PDF, page by page."""

    name = "fast_text"

    def extract(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"No PDF found at '{path}'.")

        page_chunks: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                # A light markdown marker keeps page provenance visible without
                # pretending we understood any deeper structure.
                page_chunks.append(f"<!-- page {page_number} -->\n{text.strip()}")

        return "\n\n".join(page_chunks).strip()
