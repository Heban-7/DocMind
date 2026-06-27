"""
DocMind | Phase 0 | Document Science Primer (Step 1: Explore)
============================================================

A read-only exploratory probe of a single PDF using `pdfplumber` and `pandas`.

It answers four beginner questions about a native-digital PDF:

    1. How big is the page?            (width x height, in PDF points)
    2. How many raw characters?        (glyphs embedded in the text layer)
    3. What words can we pull out?     (whitespace-separated tokens)
    4. Where does each word sit?       (its x0/y0/x1/y1 bounding box)

This file is BOTH a runnable script AND a small reusable toolkit. The
functions below (e.g. `inspect_page`, `extract_text_with_pdfplumber`) are
imported by `compare_extractors.py` so the pdfplumber logic lives in ONE
place and is never copy-pasted.

Pure Phase 0 sandbox: it only OBSERVES. No classification, no routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pdfplumber

# --- Paths (robust: resolved from the project root, not the caller's cwd) ---
# This file lives at  <project_root>/phase_0_document_science_primer/explore_pdf.py
# so parents[1] is the project root regardless of where the script is launched.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = PROJECT_ROOT / "data" / "data" / "ETHSWITCH-Annual-Report-202122.pdf"

# How many words to show in the coordinate preview table.
PREVIEW_WORD_COUNT = 5


@dataclass
class PageInspection:
    """A plain container for everything we observed about a single page."""

    pdf_path: Path
    page_count: int
    page_number: int  # 1-indexed, for human-friendly display
    width: float
    height: float
    char_count: int
    words: list[dict]


def ensure_pdf_exists(pdf_path: Path) -> None:
    """Fail early and clearly if the file is missing (the 'safe open')."""
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"Could not find a PDF at '{pdf_path}'.\n"
            f"Place a PDF there (or copy one of the corpus files) and retry."
        )


def inspect_page(pdf_path: Path, page_index: int = 0) -> PageInspection:
    """Open a PDF and collect geometry + text facts about a single page.

    Reusable: any script can call this to get structured page facts without
    re-implementing the pdfplumber plumbing.
    """
    ensure_pdf_exists(pdf_path)

    # `with` guarantees the file handle closes even if something fails.
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        return PageInspection(
            pdf_path=pdf_path,
            page_count=len(pdf.pages),
            page_number=page_index + 1,
            width=page.width,
            height=page.height,
            char_count=len(page.chars),
            words=page.extract_words(),
        )


def words_to_dataframe(
    words: list[dict], limit: int = PREVIEW_WORD_COUNT
) -> pd.DataFrame:
    """Turn pdfplumber word dicts into a clean (word, x0, y0, x1, y1) table.

    pdfplumber's origin is the TOP-LEFT corner, so y grows downward:
        x0 = left edge,  y0 = top edge,
        x1 = right edge, y1 = bottom edge.
    """
    rows = [
        {
            "word": w["text"],
            "x0": round(w["x0"], 2),
            "y0": round(w["top"], 2),
            "x1": round(w["x1"], 2),
            "y1": round(w["bottom"], 2),
        }
        for w in words[:limit]
    ]
    return pd.DataFrame(rows, columns=["word", "x0", "y0", "x1", "y1"])


def extract_text_with_pdfplumber(
    pdf_path: Path, page_range: tuple[int, int]
) -> dict:
    """Strategy 'Fast Text': read the embedded text layer across a page range.

    Reusable: `compare_extractors.py` calls this so the pdfplumber extraction
    logic is defined exactly once. `page_range` is 1-indexed and inclusive.
    Returns a dict (no timing here -- callers can time the call themselves).
    """
    ensure_pdf_exists(pdf_path)

    text_parts: list[str] = []
    raw_glyphs = 0
    tables_detected = 0

    with pdfplumber.open(pdf_path) as pdf:
        first, last = page_range
        # pdf.pages is 0-indexed; slice to the requested 1-indexed window.
        for page in pdf.pages[first - 1 : last]:
            raw_glyphs += len(page.chars)
            text_parts.append(page.extract_text() or "")
            # pdfplumber 'finds' tables via line/edge geometry (no AI).
            tables_detected += len(page.find_tables())

    text = "\n".join(text_parts)
    return {
        "text": text,
        "raw_glyphs": raw_glyphs,
        "tables_detected": tables_detected,
    }


def print_inspection(inspection: PageInspection) -> None:
    """Pretty-print a PageInspection plus the first-N-words coordinate table."""
    print("=" * 70)
    print("DocMind | Phase 0 | PDF Exploration")
    print("=" * 70)
    print(f"File              : {inspection.pdf_path}")
    print(f"Total pages       : {inspection.page_count}")
    print(f"Inspecting page   : {inspection.page_number}")
    print("-" * 70)
    print(
        f"Page width        : {inspection.width:.2f} points  "
        f"({inspection.width / 72:.2f} inches)"
    )
    print(
        f"Page height       : {inspection.height:.2f} points  "
        f"({inspection.height / 72:.2f} inches)"
    )
    print(f"Raw characters    : {inspection.char_count:,} embedded glyphs")
    print(f"Words detected    : {len(inspection.words):,}")
    print("-" * 70)

    if not inspection.words:
        print(
            "No words found. This page likely has no text layer (it may be a "
            "scanned image), so there is nothing to map."
        )
        return

    table = words_to_dataframe(inspection.words, PREVIEW_WORD_COUNT)
    print(f"Geometric coordinates of the first {PREVIEW_WORD_COUNT} words")
    print("(units = PDF points; origin = top-left corner)")
    print("-" * 70)
    print(table.to_string(index=False))
    print("=" * 70)


def main() -> None:
    inspection = inspect_page(SAMPLE_PDF)
    print_inspection(inspection)


if __name__ == "__main__":
    main()
