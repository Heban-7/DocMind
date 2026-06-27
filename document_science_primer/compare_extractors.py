"""
DocMind | Phase 0 | Document Science Primer (Step 2: Compare)
============================================================

A head-to-head bake-off between two extraction philosophies, on the SAME
pages of the SAME PDF:

    pdfplumber  ->  "Read the ink."   Fast, literal text + coordinates.
    Docling     ->  "Understand it."  Slow, AI layout/table reconstruction
                                      that emits clean structured Markdown.

This script REUSES the pdfplumber logic from `explore_pdf.py` (imported
below) so that extraction code lives in exactly one place. It only adds the
Docling side and the side-by-side scoreboard.

Pure Phase 0 sandbox: it only OBSERVES and COMPARES. No pipeline, no routing.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

# Reuse the shared paths + pdfplumber toolkit instead of re-implementing them.
from explore_pdf import (
    PROJECT_ROOT,
    SAMPLE_PDF,
    extract_text_with_pdfplumber,
)

# Only study the first N pages so the (slow) Docling run stays quick.
# Both tools look at the SAME pages for a fair, apples-to-apples comparison.
PAGE_RANGE = (1, 6)  # 1-indexed, inclusive on both ends.

# Where to drop the full text outputs for side-by-side eyeballing.
OUTPUT_DIR = PROJECT_ROOT / "playground_output"

# How many characters of each output to preview in the console.
PREVIEW_CHARS = 600


def run_pdfplumber(pdf_path: Path, page_range: tuple[int, int]) -> dict:
    """Time the reusable pdfplumber extraction and shape it for the scoreboard."""
    start = time.perf_counter()
    result = extract_text_with_pdfplumber(pdf_path, page_range)
    elapsed = time.perf_counter() - start

    return {
        "tool": "pdfplumber (Fast Text)",
        "seconds": round(elapsed, 2),
        "characters": len(result["text"]),
        "tables_detected": result["tables_detected"],
        "output_format": "plain text",
        "text": result["text"],
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
        "tables_detected": table_count,
        "output_format": "structured Markdown",
        "text": markdown,
    }


def build_scoreboard(plumber: dict, docling: dict) -> pd.DataFrame:
    """Assemble the side-by-side comparison table."""
    return pd.DataFrame(
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


def save_output(name: str, text: str) -> Path:
    """Write a full extraction result to disk for manual side-by-side review."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / name
    out_path.write_text(text, encoding="utf-8")
    return out_path


def main() -> None:
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

    print("SCOREBOARD")
    print(build_scoreboard(plumber, docling).to_string(index=False))
    print("-" * 74)

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
