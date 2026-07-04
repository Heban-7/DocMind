"""
DocMind | End-to-end pipeline runner (Phase 1 + Phase 2 + Phase 3).

This script wires the stages together:

    PDF --> [TriageAgent] --> DocumentProfile --> [ExtractionRouter] --> Engine
        --> extract() --> unified Markdown --> saved to .refinery/extractions/
        --> [ContextAwareChunker] --> LDUs --> saved to .refinery/chunks/

Usage:
    uv run python run_pipeline.py                      # uses data/data/sample.pdf
    uv run python run_pipeline.py path/to/other.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.agents.triage import TriageAgent
from src.chunking.engine import ContextAwareChunker
from src.config import CHUNKS_DIR, DEFAULT_SAMPLE_PDF, EXTRACTIONS_DIR
from src.extraction.router import ExtractionRouter
from src.models.document_profile import DocumentProfile


def run(pdf_path: str) -> tuple[DocumentProfile, Path]:
    """Triage one PDF, route it to the right engine, extract, and persist."""

    # --- Phase 1: Triage --------------------------------------------------
    triage = TriageAgent()
    profile, profile_path = triage.profile_and_save(pdf_path)

    print("=" * 72)
    print("DocMind | Full Pipeline (Triage -> Route -> Extract)")
    print("=" * 72)
    print(f"File           : {profile.source_filename}")
    print(f"Doc ID         : {profile.doc_id}")
    print(f"Origin / Layout: {profile.origin_type.value} / "
          f"{profile.layout_complexity.value}")
    print(f"Strategy tier  : {profile.strategy_tier.value}")
    print(f"Profile saved  : {profile_path}")
    print("-" * 72)

    # --- Phase 2: Route + Extract ----------------------------------------
    router = ExtractionRouter()
    engine = router.get_engine(profile)
    print(f"Routed to      : {type(engine).__name__} (name='{engine.name}')")
    print("Extracting...")

    markdown = engine.extract(profile.source_path)

    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXTRACTIONS_DIR / f"{profile.doc_id}.md"
    out_path.write_text(markdown, encoding="utf-8")

    print("-" * 72)
    print(f"Extracted chars: {len(markdown):,}")
    print(f"Markdown saved : {out_path}")

    # --- Phase 3: Chunk into RAG-ready LDUs -------------------------------
    print("-" * 72)
    print("Chunking into Logical Document Units...")
    chunker = ContextAwareChunker()
    chunks = chunker.chunk(markdown)

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    chunks_path = CHUNKS_DIR / f"{profile.doc_id}.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(chunk.model_dump_json() + "\n")

    avg_words = (
        sum(c.metadata.word_count for c in chunks) / len(chunks) if chunks else 0
    )
    print(f"Chunks created : {len(chunks)} (avg {avg_words:.0f} words/chunk)")
    print(f"Chunks saved   : {chunks_path}")
    print("=" * 72)
    return profile, out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DocMind pipeline.")
    parser.add_argument(
        "pdf",
        nargs="?",
        default=str(DEFAULT_SAMPLE_PDF),
        help="Path to a PDF (defaults to data/data/sample.pdf).",
    )
    args = parser.parse_args()
    run(args.pdf)


if __name__ == "__main__":
    main()
