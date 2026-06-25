"""
DocMind | Phase 0 | Document Science Primer
===========================================

A read-only exploratory probe of a single PDF using `pdfplumber` and `pandas`.

Goal of this script (and ONLY this script):
    Build intuition about what lives *inside* a native-digital PDF before we
    write any pipeline code. We answer four beginner questions:

        1. How big is the page? (width x height, in PDF points)
        2. How many raw characters are physically embedded in the page?
        3. What words can we pull out?
        4. Where exactly does each word sit on the page? (its bounding box)

This is a sandbox / playground. It classifies nothing, extracts no tables,
and makes no decisions. It simply *observes* and prints what it sees.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pdfplumber

# Where the document under inspection lives, relative to the project root.
SAMPLE_PDF = Path("data") / "data" / "CBE ANNUAL REPORT 2023-24.pdf"

# How many words to show in the coordinate table.
PREVIEW_WORD_COUNT = 5


def explore(pdf_path: Path) -> None:
    """Open one PDF, inspect its first page, and print human-readable findings."""

    # --- Safety gate: never assume the file is there. ----------------------
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"Could not find a PDF at '{pdf_path}'.\n"
            f"Place a PDF there (or copy one of the corpus files) and retry."
        )

    # `with` guarantees the file handle is closed even if something fails.
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)

        # We study the FIRST page only -- enough to learn the concepts.
        page = pdf.pages[0]

        # 1) Page geometry, measured in PDF "points" (1 point = 1/72 inch).
        width = page.width
        height = page.height

        # 2) Raw character count = how many individual glyphs are embedded.
        #    `page.chars` is a list of every character pdfplumber can "feel"
        #    in the text layer. A scanned image would return ~0 here.
        char_count = len(page.chars)

        # 3) Words = characters grouped by pdfplumber into whitespace-separated
        #    tokens, each carrying its own coordinates.
        words = page.extract_words()

        # --- Report the headline facts. -----------------------------------
        print("=" * 70)
        print("DocMind | Phase 0 | PDF Exploration")
        print("=" * 70)
        print(f"File              : {pdf_path}")
        print(f"Total pages       : {page_count}")
        print(f"Inspecting page   : 1")
        print("-" * 70)
        print(f"Page width        : {width:.2f} points  ({width / 72:.2f} inches)")
        print(f"Page height       : {height:.2f} points  ({height / 72:.2f} inches)")
        print(f"Raw characters    : {char_count:,} embedded glyphs on page 1")
        print(f"Words detected    : {len(words):,} on page 1")
        print("-" * 70)

        if not words:
            print(
                "No words found on page 1. This PDF page likely has no text "
                "layer (it may be a scanned image), so there is nothing to map."
            )
            return

        # 4) Build a clean table of the first N words and their bounding boxes.
        #    pdfplumber's coordinate system has its origin at the TOP-LEFT,
        #    so y grows downward:
        #        x0 = left edge,  y0 = top edge,
        #        x1 = right edge, y1 = bottom edge.
        rows = []
        for word in words[:PREVIEW_WORD_COUNT]:
            rows.append(
                {
                    "word": word["text"],
                    "x0": round(word["x0"], 2),
                    "y0": round(word["top"], 2),
                    "x1": round(word["x1"], 2),
                    "y1": round(word["bottom"], 2),
                }
            )

        table = pd.DataFrame(rows, columns=["word", "x0", "y0", "x1", "y1"])

        print(f"Geometric coordinates of the first {PREVIEW_WORD_COUNT} words")
        print("(units = PDF points; origin = top-left corner)")
        print("-" * 70)
        print(table.to_string(index=False))
        print("=" * 70)


def main() -> None:
    explore(SAMPLE_PDF)


if __name__ == "__main__":
    main()
