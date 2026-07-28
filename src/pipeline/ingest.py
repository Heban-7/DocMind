"""Shared PDF ingest pipeline (Phases 1-4) used by CLI and the API gateway."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.agents.triage import TriageAgent
from src.chunking.engine import ContextAwareChunker
from src.config import CHUNKS_DIR, EXTRACTIONS_DIR
from src.extraction.router import ExtractionRouter
from src.models.document_profile import DocumentProfile
from src.pipeline.phase4 import Phase4IndexResult, build_query_indexes

logger = logging.getLogger("docmind.pipeline")


@dataclass(frozen=True)
class IngestResult:
    """Outcome of a full document ingest (triage -> extract -> chunk -> index)."""

    profile: DocumentProfile
    extraction_path: Path
    chunks_path: Path
    chunk_count: int
    phase4: Phase4IndexResult | None


def ingest_pdf(
    pdf_path: str | Path,
    *,
    skip_phase4: bool = False,
    skip_embed: bool = False,
) -> IngestResult:
    """Run Triage -> Extract -> Chunk, then optional Phase 4 query indexes."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.name}")

    triage = TriageAgent()
    profile, _profile_path = triage.profile_and_save(str(path))
    logger.info(
        "triage doc_id=%s tier=%s pages=%s",
        profile.doc_id,
        profile.strategy_tier.value,
        profile.page_count,
    )

    router = ExtractionRouter()
    engine = router.get_engine(profile)
    markdown = engine.extract(profile.source_path)

    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
    extraction_path = EXTRACTIONS_DIR / f"{profile.doc_id}.md"
    extraction_path.write_text(markdown, encoding="utf-8")

    chunker = ContextAwareChunker()
    chunks = chunker.chunk(markdown)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    chunks_path = CHUNKS_DIR / f"{profile.doc_id}.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(chunk.model_dump_json() + "\n")

    phase4: Phase4IndexResult | None = None
    if not skip_phase4:
        phase4 = build_query_indexes(
            profile.doc_id,
            document_name=profile.source_filename,
            embed=not skip_embed,
            pageindex_llm_client=None,
        )

    return IngestResult(
        profile=profile,
        extraction_path=extraction_path,
        chunks_path=chunks_path,
        chunk_count=len(chunks),
        phase4=phase4,
    )
