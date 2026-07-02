"""
Render PDF pages to PNG images for the vision tier.

Uses pypdfium2 (already a dependency) -- a fast, lightweight renderer that does
NOT pull in PyTorch. The vision engine sends these images to a VLM.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium


def render_pages_to_png(
    file_path: str, max_pages: int | None = None, dpi: int = 150
) -> list[bytes]:
    """Render leading pages of a PDF to PNG byte blobs.

    Args:
        file_path: path to the PDF.
        max_pages: render at most this many leading pages (None = all).
        dpi: render resolution; 150 is a good text-legibility/size balance.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No PDF found at '{path}'.")

    images: list[bytes] = []
    scale = dpi / 72.0  # pypdfium2 scale is relative to 72 DPI.

    pdf = pdfium.PdfDocument(str(path))
    try:
        page_count = len(pdf)
        limit = page_count if max_pages is None else min(max_pages, page_count)
        for index in range(limit):
            page = pdf[index]
            pil_image = page.render(scale=scale).to_pil()
            buffer = BytesIO()
            pil_image.save(buffer, format="PNG")
            images.append(buffer.getvalue())
    finally:
        pdf.close()

    return images
