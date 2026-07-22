"""
Phase 4 post-chunk indexing: PageIndex + FactTable + (optional) Chroma ingest.

Kept separate from triage/extract so CLI scripts and tests can call it on an
existing ``.refinery/chunks/{doc_id}.jsonl`` without re-running the PDF path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.config import CHUNKS_DIR
from src.facts.extractor import extract_and_store_from_chunks_file
from src.facts.store import FactStore
from src.pageindex.builder import build_and_save_from_chunks_file
from src.retrieval.ingest import ingest_from_chunks_file
from src.retrieval.vector_store import ChromaLDUStore

logger = logging.getLogger("docmind.phase4")


@dataclass
class Phase4IndexResult:
    doc_id: str
    document_name: str
    pageindex_path: Path | None
    pageindex_sections: int
    facts_written: int
    chunks_embedded: int
    chroma_total: int
    embedded: bool


def build_query_indexes(
    doc_id: str,
    *,
    document_name: str = "",
    chunks_dir: Path | None = None,
    embed: bool = True,
    summarize_pageindex: bool = True,
    pageindex_llm_client=None,
    chroma_store: ChromaLDUStore | None = None,
    fact_store: FactStore | None = None,
    embedder=None,
) -> Phase4IndexResult:
    """Build PageIndex + FactTable, and optionally embed LDUs into Chroma.

    PageIndex summaries default to extractive (``pageindex_llm_client=None``)
    so indexing stays free unless you pass an LLM. Chroma ingest uses OpenAI
    embeddings when ``embed=True``.
    """
    chunks_dir = chunks_dir or CHUNKS_DIR
    chunks_path = chunks_dir / f"{doc_id}.jsonl"
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"No chunks file for doc_id={doc_id!r} at {chunks_path}. "
            "Run run_pipeline.py first (or pass a doc that already has chunks)."
        )

    index, pageindex_path = build_and_save_from_chunks_file(
        doc_id,
        chunks_dir=chunks_dir,
        source_filename=document_name,
        summarize=summarize_pageindex,
        llm_client=pageindex_llm_client,
    )
    section_count = len(index.iter_nodes())

    facts = extract_and_store_from_chunks_file(
        doc_id,
        document_name=document_name,
        chunks_dir=chunks_dir,
        store=fact_store,
        use_llm=False,
    )

    chunks_embedded = 0
    chroma_total = 0
    if embed:
        ingest = ingest_from_chunks_file(
            doc_id,
            document_name=document_name,
            chunks_dir=chunks_dir,
            store=chroma_store,
            embedder=embedder,
        )
        chunks_embedded = ingest.chunks_ingested
        chroma_total = ingest.collection_total

    logger.info(
        "phase4 doc_id=%s pageindex=%s facts=%d embedded=%s chunks=%d",
        doc_id,
        pageindex_path,
        facts.facts_written,
        embed,
        chunks_embedded,
    )
    return Phase4IndexResult(
        doc_id=doc_id,
        document_name=document_name,
        pageindex_path=pageindex_path,
        pageindex_sections=section_count,
        facts_written=facts.facts_written,
        chunks_embedded=chunks_embedded,
        chroma_total=chroma_total,
        embedded=embed,
    )


def resolve_pdf_path(doc_id: str, pdf: str | Path | None = None) -> Path | None:
    """Best-effort PDF path from explicit arg or saved triage profile."""
    if pdf:
        path = Path(pdf)
        return path if path.exists() else None
    from src.config import PROFILES_DIR

    profile_path = PROFILES_DIR / f"{doc_id}.json"
    if not profile_path.exists():
        return None
    try:
        import json

        data = json.loads(profile_path.read_text(encoding="utf-8"))
        source = data.get("source_path") or ""
        if source:
            path = Path(source)
            if not path.is_absolute():
                from src.config import PROJECT_ROOT

                path = PROJECT_ROOT / path
            return path if path.exists() else None
    except Exception:
        return None
    return None
