"""
DocMind | End-to-end pipeline runner (Phases 1-4).

Wires the stages together:

    PDF --> Triage --> Extract --> Chunk (LDUs)
        --> PageIndex + FactTable + Chroma (Phase 4 query indexes)

Usage:
    uv run python run_pipeline.py                      # sample.pdf, full Phase 4
    uv run python run_pipeline.py path/to/other.pdf
    uv run python run_pipeline.py --skip-embed         # free indexes only (no OpenAI embeds)
    uv run python run_pipeline.py --skip-phase4        # stop after chunking
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.config import DEFAULT_SAMPLE_PDF
from src.models.document_profile import DocumentProfile
from src.pipeline.ingest import ingest_pdf


def run(
    pdf_path: str,
    *,
    skip_phase4: bool = False,
    skip_embed: bool = False,
) -> tuple[DocumentProfile, Path]:
    """Triage one PDF, extract, chunk, and optionally build query indexes."""
    result = ingest_pdf(
        pdf_path,
        skip_phase4=skip_phase4,
        skip_embed=skip_embed,
    )
    profile = result.profile

    print("=" * 72)
    print("DocMind | Full Pipeline (Triage -> Extract -> Chunk -> Index)")
    print("=" * 72)
    print(f"File           : {profile.source_filename}")
    print(f"Doc ID         : {profile.doc_id}")
    print(f"Origin / Layout: {profile.origin_type.value} / "
          f"{profile.layout_complexity.value}")
    print(f"Strategy tier  : {profile.strategy_tier.value}")
    print("-" * 72)
    print(f"Extracted chars: {result.extraction_path.stat().st_size:,} (file bytes)")
    print(f"Markdown saved : {result.extraction_path}")
    print("-" * 72)
    print(f"Chunks created : {result.chunk_count}")
    print(f"Chunks saved   : {result.chunks_path}")

    if skip_phase4 or result.phase4 is None:
        print("-" * 72)
        print("Phase 4 skipped (--skip-phase4).")
    else:
        phase4 = result.phase4
        print("-" * 72)
        print("Building Phase 4 query indexes (PageIndex + FactTable"
              + (" + Chroma" if not skip_embed else ", Chroma skipped")
              + ")...")
        print(f"PageIndex      : {phase4.pageindex_path} "
              f"({phase4.pageindex_sections} sections)")
        print(f"Facts written  : {phase4.facts_written}")
        if phase4.embedded:
            print(f"Chroma upsert  : {phase4.chunks_embedded} chunks "
                  f"(collection total={phase4.chroma_total})")
        else:
            print("Chroma         : skipped (--skip-embed)")

    print("=" * 72)
    return profile, result.extraction_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the DocMind pipeline (Phases 1-4)."
    )
    parser.add_argument(
        "pdf",
        nargs="?",
        default=str(DEFAULT_SAMPLE_PDF),
        help="Path to a PDF (defaults to data/data/sample.pdf).",
    )
    parser.add_argument(
        "--skip-phase4",
        action="store_true",
        help="Stop after chunking (no PageIndex / FactTable / Chroma).",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Build PageIndex + FactTable but skip Chroma (no embedding API cost).",
    )
    args = parser.parse_args()
    run(args.pdf, skip_phase4=args.skip_phase4, skip_embed=args.skip_embed)


if __name__ == "__main__":
    main()
