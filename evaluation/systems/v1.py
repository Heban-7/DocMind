"""Run DocMind V1 exactly as it ships and capture its raw outputs.

The V1 pipeline is called step by step (the same calls ``ingest_pdf`` makes)
so each stage can be timed. Nothing in ``src`` is modified.

The caller must set ``DOCMIND_REFINERY_DIR`` (and other environment) before
this module is imported, because V1 reads its paths at import time.
"""

from __future__ import annotations

import re
import sqlite3
import time
import traceback
from pathlib import Path

from evaluation.systems.usage import install, measured

_PAGE_MARK = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.IGNORECASE)
_FAILED_MARK = re.compile(r"<!--\s*pages?\s+(\d+)(?:-(\d+))?\s+failed", re.IGNORECASE)


def split_pages(markdown: str) -> tuple[dict[int, str], set[int]]:
    """Split V1 markdown on its ``<!-- page N -->`` markers.

    Text before the first marker (or a document with no markers at all) is
    attributed to page 1, which is what V1's chunker does too.
    """
    pages: dict[int, str] = {}
    current = 1
    pos = 0
    for m in _PAGE_MARK.finditer(markdown):
        pages[current] = pages.get(current, "") + markdown[pos : m.start()]
        current = int(m.group(1))
        pos = m.end()
    pages[current] = pages.get(current, "") + markdown[pos:]
    failed: set[int] = set()
    for m in _FAILED_MARK.finditer(markdown):
        a = int(m.group(1))
        b = int(m.group(2) or a)
        failed.update(range(a, b + 1))
    return {p: t.strip() for p, t in pages.items()}, failed


def _device() -> str:
    from src.config import EXTRACTION_DEVICE
    from src.extraction._docling_support import _resolve_device

    dev, _ = _resolve_device(EXTRACTION_DEVICE)
    return str(dev.value if hasattr(dev, "value") else dev)


def run_document(pdf_path: Path, *, embed: bool = True) -> dict:
    """Triage, extract, chunk and index one PDF with V1. Returns raw outputs."""
    install()
    from src.agents.triage import TriageAgent
    from src.chunking.engine import ContextAwareChunker
    from src.config import CHUNKS_DIR, EXTRACTIONS_DIR, FACTS_DB_PATH
    from src.extraction.router import ExtractionRouter
    from src.pipeline.phase4 import build_query_indexes

    out: dict = {"file": pdf_path.name, "device": _device(), "error": None, "stages": {}}
    try:
        with measured() as m:
            profile, _ = TriageAgent().profile_and_save(str(pdf_path))
        out["stages"]["triage"] = m
        out.update(
            doc_id=profile.doc_id,
            tier=profile.strategy_tier.value,
            origin=profile.origin_type.value,
            layout=profile.layout_complexity.value,
            n_pages=profile.page_count,
        )
        engine = ExtractionRouter().get_engine(profile)
        out["engine"] = getattr(engine, "name", type(engine).__name__)
        if out["engine"] == "vision_augmented" and getattr(engine, "client", None) is None:
            out["engine"] = "vision_augmented:ocr_fallback"
        with measured() as m:
            markdown = engine.extract(profile.source_path)
        out["stages"]["extract"] = m
        EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
        (EXTRACTIONS_DIR / f"{profile.doc_id}.md").write_text(markdown, encoding="utf-8")

        with measured() as m:
            chunks = ContextAwareChunker().chunk(markdown)
            CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
            with open(CHUNKS_DIR / f"{profile.doc_id}.jsonl", "w", encoding="utf-8") as fh:
                for c in chunks:
                    fh.write(c.model_dump_json() + "\n")
        out["stages"]["chunk"] = m
        out["chunks"] = len(chunks)

        with measured() as m:
            idx = build_query_indexes(
                profile.doc_id,
                document_name=profile.source_filename,
                embed=embed,
                pageindex_llm_client=None,
            )
        out["stages"]["index"] = m
        out["facts_written"] = idx.facts_written
        out["chunks_embedded"] = idx.chunks_embedded

        pages, failed = split_pages(markdown)
        out["pages_text"] = {str(k): v for k, v in pages.items()}
        out["failed_pages"] = sorted(failed)
        out["facts"] = _facts_for(FACTS_DB_PATH, profile.doc_id)
    except Exception as exc:  # record and continue with the next document
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()[-2000:]
    out["total_seconds"] = round(sum(s.get("seconds", 0.0) for s in out["stages"].values()), 2)
    return out


def _facts_for(db_path: Path, doc_id: str) -> list[dict]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT metric, value, value_text, unit, period, page_number FROM facts WHERE doc_id = ?",
            (doc_id,),
        ).fetchall()
    finally:
        conn.close()
    keys = ("metric", "value", "value_text", "unit", "period", "page_number")
    return [dict(zip(keys, r)) for r in rows]


def ask(doc_id: str, pdf_path: Path, question: str, *, model: str | None = None) -> dict:
    """Ask V1 one question about one document; return answer, citations, usage."""
    install()
    from src.agents.query_agent import build_query_agent
    from src.llm.factory import get_text_client
    from src.retrieval.ingest import semantic_search

    llm = get_text_client(model=model) if model else None
    agent = build_query_agent(doc_id, pdf_path=pdf_path, llm=llm)
    start = time.perf_counter()
    with measured() as m:
        answer = agent.ask(question)
    latency = time.perf_counter() - start
    with measured() as r:
        hits = semantic_search(question, doc_id=doc_id, top_k=5)
    return {
        "answer": answer.answer,
        "cited_pages": [c.page_number for c in answer.provenance.citations],
        "tools": [t.tool.value for t in answer.tool_trace],
        "latency_s": round(latency, 3),
        "first_token_s": round(latency, 3),  # V1 streams only after the full answer
        "usage": m,
        "retrieval_top5_pages": sorted({p for h in hits for p in (h.page_numbers or [])}),
        "retrieval_usage": r,
    }
