"""Document ingest: extract -> chunk -> index, stored per tenant in Postgres.

    result = ingest_document(pdf_path, principal=principal, file_name="report.pdf")

Steps, each timed into ``documents.stats``:

1. hash the file; the same file uploaded twice by one tenant is processed once
2. store the PDF (blob storage) and create the ``documents`` row (processing)
3. V2 extraction into the structured document model, saved next to the PDF
4. render Markdown, chunk, build the PageIndex and the FactTable
5. embed the chunks into pgvector
6. write the per-page ledger and mark the document ``ready`` (or ``failed``)

``index_document`` (steps 4-5) also works against in-memory stores, for
unit tests and the offline demo.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.chunking.engine import ContextAwareChunker
from src.chunking.models import DocumentChunk
from src.document.model import DocumentModel
from src.document.render import render_markdown
from src.facts.extractor import extract_and_store
from src.pageindex.builder import build_page_index
from src.retrieval.embeddings import EmbeddingClient
from src.retrieval.ingest import ingest_chunks
from src.stores.base import Stores

logger = logging.getLogger("docmind.pipeline")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class IndexResult:
    chunk_count: int
    facts_written: int
    pageindex_sections: int
    embedded: bool
    seconds: dict[str, float] = field(default_factory=dict)


def index_document(
    model: DocumentModel,
    *,
    doc_id: str,
    document_name: str,
    stores: Stores,
    embedder: EmbeddingClient | None = None,
    embed: bool = True,
) -> tuple[IndexResult, list[DocumentChunk]]:
    """Chunk a document model and write chunks, facts and PageIndex to ``stores``."""
    seconds: dict[str, float] = {}

    t = time.perf_counter()
    markdown = render_markdown(model)
    chunks = ContextAwareChunker().chunk(markdown)
    seconds["chunk"] = time.perf_counter() - t

    t = time.perf_counter()
    index = build_page_index(chunks, doc_id=doc_id, source_filename=document_name, summarize=True, llm_client=None)
    stores.pageindex.save(index)
    facts = extract_and_store(chunks, doc_id=doc_id, document_name=document_name, store=stores.facts)
    seconds["index"] = time.perf_counter() - t

    t = time.perf_counter()
    ingest = ingest_chunks(
        chunks, doc_id=doc_id, document_name=document_name, store=stores.chunks, embedder=embedder, embed=embed
    )
    seconds["embed"] = time.perf_counter() - t

    result = IndexResult(
        chunk_count=len(chunks),
        facts_written=facts.facts_written,
        pageindex_sections=len(index.iter_nodes()),
        embedded=ingest.embedded,
        seconds={k: round(v, 3) for k, v in seconds.items()},
    )
    return result, chunks


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    file_name: str
    page_count: int
    status: str
    deduplicated: bool
    chunk_count: int = 0
    facts_written: int = 0
    pages_needing_review: int = 0
    engines: dict[str, int] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


def _engines(model: DocumentModel) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in model.pages:
        out[p.quality.engine] = out.get(p.quality.engine, 0) + 1
    return dict(sorted(out.items()))


def _domain_hint(model: DocumentModel) -> str:
    try:
        from src.agents.domain import KeywordDomainClassifier

        text = "\n".join(p.body_text() for p in model.pages[:5])
        hint, _ = KeywordDomainClassifier().classify(text)
        return str(getattr(hint, "value", hint))
    except Exception:  # the hint only helps routing; never fail an ingest on it
        return ""


def ingest_document(
    pdf_path: str | Path,
    *,
    principal,
    file_name: str | None = None,
    embedder: EmbeddingClient | None = None,
    embed: bool = True,
    vision_client=None,
    allow_vision: bool = True,
    model: DocumentModel | None = None,
    blobs=None,
    stores: Stores | None = None,
) -> IngestResult:
    """Ingest one PDF for ``principal``'s tenant. Idempotent per file content.

    ``model`` skips extraction with an already extracted document model (the
    benchmark reuses the M2 extraction this way). ``blobs`` and ``stores``
    default to local file storage and the tenant's Postgres stores.
    """
    from src.db import repos
    from src.storage.blobs import document_model_key, document_source_key, get_blob_store
    from src.stores.pg import pg_stores

    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    name = file_name or path.name
    tenant = principal.tenant_id
    blobs = blobs or get_blob_store()
    stores = stores or pg_stores(tenant)

    t0 = time.perf_counter()
    sha = sha256_file(path)
    existing = repos.find_document_by_sha(tenant, sha)
    if existing is not None and existing.status == "ready":
        logger.info("ingest dedupe tenant=%s doc=%s", tenant, existing.id)
        return IngestResult(
            document_id=existing.id,
            file_name=existing.file_name,
            page_count=existing.page_count,
            status=existing.status,
            deduplicated=True,
            pages_needing_review=existing.pages_needing_review,
            stats=existing.stats,
        )

    if existing is not None:  # a failed or interrupted earlier attempt: retry in place
        doc_id = existing.id
        storage_key = existing.storage_key
        repos.mark_document_processing(tenant, doc_id, file_name=name)
    else:
        doc_id = repos.new_document_id()
        storage_key = document_source_key(tenant, doc_id)
        repos.create_document(principal, document_id=doc_id, sha256=sha, file_name=name, storage_key=storage_key)

    try:
        blobs.put_file(storage_key, path)
        stored_pdf = blobs.local_path(storage_key)

        t = time.perf_counter()
        if model is None:
            from src.document.extract import extract_document

            model = extract_document(stored_pdf, vision_client=vision_client, allow_vision=allow_vision)
        model = model.model_copy(update={"doc_id": doc_id, "file_name": name})
        extract_s = time.perf_counter() - t
        model_key = document_model_key(tenant, doc_id)
        blobs.put_bytes(model_key, model.model_dump_json().encode("utf-8"))

        result, _ = index_document(model, doc_id=doc_id, document_name=name, stores=stores, embedder=embedder, embed=embed)

        ledger = model.ledger()
        engines = _engines(model)
        stats = {
            "seconds": {"extract": round(extract_s, 3), **result.seconds, "total": round(time.perf_counter() - t0, 3)},
            "engines": engines,
            "chunks": result.chunk_count,
            "facts": result.facts_written,
            "pageindex_sections": result.pageindex_sections,
            "embedded": result.embedded,
            "extraction_cost_usd": round(sum(float(p.get("cost_usd") or 0.0) for p in ledger), 6),
        }
        repos.mark_document_ready(
            tenant,
            doc_id,
            page_count=len(model.pages),
            model_key=model_key,
            ledger=ledger,
            domain_hint=_domain_hint(model),
            stats=stats,
        )
    except Exception as exc:
        logger.exception("ingest failed tenant=%s doc=%s", tenant, doc_id)
        repos.mark_document_failed(tenant, doc_id, f"{type(exc).__name__}: {exc}")
        raise

    logger.info("ingest ready tenant=%s doc=%s pages=%d chunks=%d", tenant, doc_id, len(model.pages), result.chunk_count)
    return IngestResult(
        document_id=doc_id,
        file_name=name,
        page_count=len(model.pages),
        status="ready",
        deduplicated=False,
        chunk_count=result.chunk_count,
        facts_written=result.facts_written,
        pages_needing_review=sum(1 for p in ledger if p.get("needs_review")),
        engines=engines,
        stats=stats,
    )
