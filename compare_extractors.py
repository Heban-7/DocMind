"""
DocMind | Phase 0 | Extraction Bake-Off: pdfplumber vs. Docling
==============================================================

In `explore_pdf.py` we learned to *see* the raw atoms of a PDF (characters,
words, coordinates) using the FAST, simple tool: pdfplumber.

Now we put that tool head-to-head against a SMART, heavyweight tool: Docling
(IBM Research). Same PDF, same pages -- two very different philosophies:

    pdfplumber  ->  "Read the ink." Pulls the literal text/coordinates that
                    are already embedded. Microscopically fast. Knows nothing
                    about layout, reading order, or what a "table" means.

    Docling     ->  "Understand the page." Runs AI layout + table models to
                    rebuild reading order, detect tables/figures, and emit
                    clean structured Markdown. Slower & heavier, but it
                    preserves MEANING and STRUCTURE.

This script is still pure Phase 0 sandbox: it only OBSERVES and COMPARES.
It builds no pipeline, makes no routing decisions, and classifies nothing.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pdfplumber
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

# The document we inspect, relative to the project root.
SAMPLE_PDF = Path("data") / "data" / "sample.pdf"

# Only study the first N pages so the (slow) Docling run stays quick.
# Both tools look at the SAME pages for a fair, apples-to-apples comparison.
PAGE_RANGE = (1, 6)  # 1-indexed, inclusive on both ends.

# Where to drop the full text outputs for side-by-side eyeballing.
OUTPUT_DIR = Path("playground_output")

# How many characters of each output to preview in the console.
PREVIEW_CHARS = 600


def run_pdfplumber(pdf_path: Path, page_range: tuple[int, int]) -> dict:
    """Strategy 'Fast Text': read the embedded text layer directly."""

    start = time.perf_counter()

    text_parts: list[str] = []
    char_count = 0
    table_count = 0

    with pdfplumber.open(pdf_path) as pdf:
        first, last = page_range
        # pdf.pages is 0-indexed; slice to the requested 1-indexed window.
        for page in pdf.pages[first - 1 : last]:
            char_count += len(page.chars)
            text_parts.append(page.extract_text() or "")
            # pdfplumber can *find* table-like grids via line/edge geometry.
            table_count += len(page.find_tables())

    elapsed = time.perf_counter() - start
    full_text = "\n".join(text_parts)

    return {
        "tool": "pdfplumber (Fast Text)",
        "seconds": round(elapsed, 2),
        "characters": len(full_text),
        "raw_glyphs": char_count,
        "tables_detected": table_count,
        "output_format": "plain text",
        "text": full_text,
    }


def run_docling(pdf_path: Path, page_range: tuple[int, int]) -> dict:
    """Strategy 'Layout-Aware': let AI models rebuild structure + tables."""

    start = time.perf_counter()

    # Our sample is a NATIVE-DIGITAL PDF, so it already has a text layer and
    # we do NOT need OCR. Turning OCR off is both correct AND cheaper here --
    # OCR is only needed for scanned/image PDFs. The layout + table-structure
    # AI models still run, which is the whole point of the comparison.
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    # NOTE: the FIRST ever call downloads the layout/table models (~hundreds
    # of MB) from Hugging Face. Subsequent runs use the local cache.
    result = converter.convert(pdf_path, page_range=page_range)
    document = result.document

    # Docling's superpower: export clean, structure-preserving Markdown,
    # with tables rendered as real Markdown tables (| col | col |).
    markdown = document.export_to_markdown()
    table_count = len(document.tables)

    elapsed = time.perf_counter() - start

    return {
        "tool": "Docling (Layout-Aware)",
        "seconds": round(elapsed, 2),
        "characters": len(markdown),
        "raw_glyphs": None,  # Docling thinks in structure, not raw glyphs.
        "tables_detected": table_count,
        "output_format": "structured Markdown",
        "text": markdown,
    }


def save_output(name: str, text: str) -> Path:
    """Write a full extraction result to disk for manual side-by-side review."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / name
    out_path.write_text(text, encoding="utf-8")
    return out_path


def main() -> None:
    if not SAMPLE_PDF.exists():
        raise FileNotFoundError(
            f"Could not find a PDF at '{SAMPLE_PDF}'. "
            f"Copy a corpus PDF there and retry."
        )

    print("=" * 74)
    print("DocMind | Phase 0 | pdfplumber vs. Docling")
    print("=" * 74)
    print(f"File        : {SAMPLE_PDF}")
    print(f"Pages       : {PAGE_RANGE[0]}-{PAGE_RANGE[1]} (same window for both tools)")
    print("-" * 74)

    print("Running pdfplumber (fast text)...")
    plumber = run_pdfplumber(SAMPLE_PDF, PAGE_RANGE)
    print(f"  done in {plumber['seconds']}s")

    print("Running Docling (layout-aware AI -- first run downloads models)...")
    docling = run_docling(SAMPLE_PDF, PAGE_RANGE)
    print(f"  done in {docling['seconds']}s")
    print("-" * 74)

    # --- The scoreboard. --------------------------------------------------
    comparison = pd.DataFrame(
        [
            {
                "metric": "Processing time (s)",
                "pdfplumber": plumber["seconds"],
                "Docling": docling["seconds"],
            },
            {
                "metric": "Output length (chars)",
                "pdfplumber": plumber["characters"],
                "Docling": docling["characters"],
            },
            {
                "metric": "Tables detected",
                "pdfplumber": plumber["tables_detected"],
                "Docling": docling["tables_detected"],
            },
            {
                "metric": "Output format",
                "pdfplumber": plumber["output_format"],
                "Docling": docling["output_format"],
            },
        ]
    )
    print("SCOREBOARD")
    print(comparison.to_string(index=False))
    print("-" * 74)

    # --- Save full outputs + show a quick preview of each. ----------------
    plumber_path = save_output("pdfplumber_output.txt", plumber["text"])
    docling_path = save_output("docling_output.md", docling["text"])

    print("PREVIEW | pdfplumber (first chars):")
    print(plumber["text"][:PREVIEW_CHARS].strip() or "(no text)")
    print("." * 74)
    print("PREVIEW | Docling (first chars):")
    print(docling["text"][:PREVIEW_CHARS].strip() or "(no text)")
    print("=" * 74)
    print(f"Full pdfplumber text saved to : {plumber_path}")
    print(f"Full Docling Markdown saved to: {docling_path}")
    print("Open both files to see how each tool preserves (or loses) structure.")
    print("=" * 74)


if __name__ == "__main__":
    main()
