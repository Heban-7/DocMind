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

from src.agents.triage import TriageAgent
from src.chunking.engine import ContextAwareChunker
from src.config import CHUNKS_DIR, DEFAULT_SAMPLE_PDF, EXTRACTIONS_DIR
from src.extraction.router import ExtractionRouter
from src.models.document_profile import DocumentProfile
from src.pipeline.phase4 import build_query_indexes


def run(
    pdf_path: str,
    *,
    skip_phase4: bool = False,
    skip_embed: bool = False,
) -> tuple[DocumentProfile, Path]:
    """Triage one PDF, extract, chunk, and optionally build query indexes."""

    # --- Phase 1: Triage --------------------------------------------------
    triage = TriageAgent()
    profile, profile_path = triage.profile_and_save(pdf_path)

    print("=" * 72)
    print("DocMind | Full Pipeline (Triage -> Extract -> Chunk -> Index)")
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

    # --- Phase 4: Query indexes ------------------------------------------
    if skip_phase4:
        print("-" * 72)
        print("Phase 4 skipped (--skip-phase4).")
    else:
        print("-" * 72)
        print("Building Phase 4 query indexes (PageIndex + FactTable"
              + (" + Chroma" if not skip_embed else ", Chroma skipped")
              + ")...")
        result = build_query_indexes(
            profile.doc_id,
            document_name=profile.source_filename,
            embed=not skip_embed,
            pageindex_llm_client=None,  # extractive summaries = free
        )
        print(f"PageIndex      : {result.pageindex_path} "
              f"({result.pageindex_sections} sections)")
        print(f"Facts written  : {result.facts_written}")
        if result.embedded:
            print(f"Chroma upsert  : {result.chunks_embedded} chunks "
                  f"(collection total={result.chroma_total})")
        else:
            print("Chroma         : skipped (--skip-embed)")

    print("=" * 72)
    return profile, out_path


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
