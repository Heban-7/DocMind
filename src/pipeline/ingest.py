"""Document ingest: extract -> chunk -> index, stored per tenant in Postgres.

Two halves:

* ``submit_document`` (the API, milliseconds): hash the file, store it,
  create the document as ``queued`` and add a job. The same file uploaded
  twice by one tenant is processed once.
* ``process_document`` (the worker, minutes): read every page's text layer,
  index those pages right away so the document is searchable early, then
  read the table and scanned pages with Docling in parallel lanes, index the
  full result and mark the document ``ready``. Progress is written per page.

``ingest_document`` does both in one call, for the CLI and the benchmark.
``index_document`` (chunk, facts, PageIndex, vectors) also works against
in-memory stores, for unit tests and the offline demo.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.chunking.engine import ContextAwareChunker
from src.chunking.models import DocumentChunk
from src.document.model import DocumentModel
from src.document.render import render_markdown
from src.facts.typed import facts_from_model
from src.pageindex.builder import build_page_index
from src.retrieval.embeddings import EmbeddingClient
from src.retrieval.ingest import ingest_chunks
from src.stores.base import Stores

logger = logging.getLogger("docmind.pipeline")

_PDFIUM_LOCK = threading.Lock()


class TooManyPagesError(ValueError):
    pass


def max_pages() -> int:
    return int(os.getenv("DOCMIND_MAX_PAGES", "500"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def count_pages(path: Path) -> int:
    """Page count without parsing the content (pdfium is not thread-safe)."""
    import pypdfium2 as pdfium

    with _PDFIUM_LOCK:
        doc = pdfium.PdfDocument(str(path))
        try:
            return len(doc)
        finally:
            doc.close()


@dataclass
class IndexResult:
    chunk_count: int
    facts_written: int
    pageindex_sections: int
    embedded: bool
    texts_embedded: int = 0
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
    # Facts come from the model itself (cells, boxes, pages), not from the Markdown.
    facts_written = stores.facts.replace_doc_facts(doc_id, facts_from_model(model, doc_id=doc_id, document_name=document_name))
    seconds["index"] = time.perf_counter() - t

    t = time.perf_counter()
    ingest = ingest_chunks(
        chunks, doc_id=doc_id, document_name=document_name, store=stores.chunks, embedder=embedder, embed=embed
    )
    seconds["embed"] = time.perf_counter() - t

    result = IndexResult(
        chunk_count=len(chunks),
        facts_written=facts_written,
        pageindex_sections=len(index.iter_nodes()),
        embedded=ingest.embedded,
        texts_embedded=ingest.texts_embedded,
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


def _result_from_row(row, *, deduplicated: bool) -> IngestResult:
    return IngestResult(
        document_id=row.id,
        file_name=row.file_name,
        page_count=row.page_count,
        status=row.status,
        deduplicated=deduplicated,
        pages_needing_review=row.pages_needing_review,
        engines=(row.stats or {}).get("engines") or {},
        stats=row.stats or {},
    )


# --- Submit (API side) -----------------------------------------------------------


def submit_document(
    pdf_path: str | Path,
    *,
    principal,
    file_name: str | None = None,
    blobs=None,
    enqueue: bool = True,
) -> IngestResult:
    """Store a PDF and queue it for processing; returns at once.

    With ``enqueue=False`` the document is created as ``processing`` with no
    job, for a caller that processes it right away (``ingest_document``).
    """
    from src.db import repos
    from src.storage.blobs import document_source_key, get_blob_store

    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    name = file_name or path.name
    tenant = principal.tenant_id
    blobs = blobs or get_blob_store()

    sha = sha256_file(path)
    existing = repos.find_document_by_sha(tenant, sha)
    if existing is not None:
        if existing.status == "failed" and enqueue:
            blobs.put_file(existing.storage_key, path)
            row = repos.requeue_document(principal, existing.id, file_name=name)
            return _result_from_row(row, deduplicated=False)
        if existing.status == "failed" or (not enqueue and existing.status != "ready"):
            blobs.put_file(existing.storage_key, path)
            repos.mark_document_processing(tenant, existing.id, file_name=name)
            return _result_from_row(repos.require_document(tenant, existing.id), deduplicated=False)
        # ready, or already queued / being processed: the same file is not read twice
        return _result_from_row(existing, deduplicated=True)

    try:
        pages = count_pages(path)
    except Exception as exc:
        raise ValueError(f"The PDF could not be opened: {exc}") from exc
    if pages > max_pages():
        raise TooManyPagesError(f"The PDF has {pages} pages; the limit is {max_pages()}.")
    doc_id = repos.new_document_id()
    storage_key = document_source_key(tenant, doc_id)
    blobs.put_file(storage_key, path)
    row = repos.create_document(
        principal,
        document_id=doc_id,
        sha256=sha,
        file_name=name,
        storage_key=storage_key,
        status="queued" if enqueue else "processing",
        page_count=pages,
        enqueue=enqueue,
    )
    logger.info("submitted tenant=%s doc=%s pages=%d queued=%s", tenant, doc_id, pages, enqueue)
    return _result_from_row(row, deduplicated=False)


# --- Process (worker side) ---------------------------------------------------------


class _Progress:
    """Writes stage and page count to the document row, at most once a second."""

    def __init__(self, tenant_id: str, document_id: str, interval: float = 1.0):
        self.tenant_id, self.document_id, self.interval = tenant_id, document_id, interval
        self._last = 0.0
        self._lock = threading.Lock()

    def __call__(self, stage: str, done: int, total: int, *, force: bool = False) -> None:
        from src.db import repos

        now = time.monotonic()
        with self._lock:
            if not force and now - self._last < self.interval and done < total:
                return
            self._last = now
        try:
            repos.set_progress(self.tenant_id, self.document_id, stage=stage, pages_done=done, page_count=total)
        except Exception as exc:  # progress is best effort
            logger.warning("progress update failed: %s", exc)


def process_document(
    tenant_id: str,
    document_id: str,
    *,
    embedder: EmbeddingClient | None = None,
    embed: bool = True,
    vision_client=None,
    allow_vision: bool = True,
    model: DocumentModel | None = None,
    blobs=None,
    stores: Stores | None = None,
    preview: bool = True,
) -> IngestResult:
    """Extract and index one stored document; marks it ``ready``.

    Raises on failure; the caller (worker or ``ingest_document``) decides
    whether the document is marked failed or retried. ``model`` skips
    extraction with an already extracted document model (the benchmark reuses
    an earlier run's extraction this way).
    """
    from src.db import repos
    from src.document.extract import extract_document, preview_model, triage_document
    from src.storage.blobs import document_model_key, get_blob_store
    from src.stores.pg import pg_stores

    blobs = blobs or get_blob_store()
    stores = stores or pg_stores(tenant_id)
    doc = repos.require_document(tenant_id, document_id)
    name = doc.file_name
    repos.mark_document_processing(tenant_id, document_id)
    progress = _Progress(tenant_id, document_id)
    t0 = time.perf_counter()
    seconds: dict[str, float] = {}
    first_searchable: list[float] = []

    preview_lock = threading.Lock()

    def index_preview(model_: DocumentModel) -> None:
        with preview_lock:
            t = time.perf_counter()
            m = model_.model_copy(update={"doc_id": document_id, "file_name": name})
            res, _ = index_document(m, doc_id=document_id, document_name=name, stores=stores, embedder=embedder, embed=embed)
            # A scan has no text layer: nothing can be searched until OCR is done.
            if res.chunk_count and res.embedded:
                repos.mark_searchable(tenant_id, document_id)
                if not first_searchable:
                    first_searchable.append(time.perf_counter() - t0)
            seconds["preview"] = seconds.get("preview", 0.0) + time.perf_counter() - t

    def index_preview_safely(model_: DocumentModel) -> None:
        try:
            index_preview(model_)
        except Exception:  # the preview is a head start only; the full index follows
            logger.exception("preview index failed doc=%s", document_id)

    pdf = blobs.local_path(doc.storage_key)
    if model is None:
        t = time.perf_counter()
        tri = triage_document(
            pdf,
            on_progress=lambda stage, done, total: progress(stage, done, total),
            checkpoint=(lambda partial: index_preview_safely(preview_model(partial))) if preview else None,
        )
        seconds["reading"] = time.perf_counter() - t - seconds.get("preview", 0.0)
        # The text layer alone already answers questions on most pages. Its
        # index is built while the table and scanned pages are read: the
        # index mostly waits on the embedding API, the reading on the CPU.
        background = None
        if preview and any(r != "text" for r in tri.routes.values()):
            background = threading.Thread(target=index_preview_safely, args=(preview_model(tri),), daemon=True)
            background.start()
        t = time.perf_counter()
        try:
            model = extract_document(
                pdf,
                vision_client=vision_client,
                allow_vision=allow_vision,
                triage=tri,
                on_progress=lambda stage, done, total: progress(stage, done, total),
            )
        finally:
            if background is not None:
                background.join()  # the full index must replace the preview, not race it
        seconds["layout"] = time.perf_counter() - t
        extract_s = model.seconds
    else:
        extract_s = 0.0
    progress("indexing", len(model.pages), len(model.pages), force=True)
    model = model.model_copy(update={"doc_id": document_id, "file_name": name})
    model_key = document_model_key(tenant_id, document_id)
    blobs.put_bytes(model_key, model.model_dump_json().encode("utf-8"))

    result, _ = index_document(model, doc_id=document_id, document_name=name, stores=stores, embedder=embedder, embed=embed)
    ledger = model.ledger()
    engines = _engines(model)
    total = time.perf_counter() - t0
    stats = {
        "seconds": {
            "extract": round(extract_s, 3),
            **{k: round(v, 3) for k, v in seconds.items()},
            **result.seconds,
            "total": round(total, 3),
        },
        "first_searchable_s": round(first_searchable[0], 3) if first_searchable else round(total, 3),
        "engines": engines,
        "chunks": result.chunk_count,
        "facts": result.facts_written,
        "texts_embedded": result.texts_embedded,
        "pageindex_sections": result.pageindex_sections,
        "embedded": result.embedded,
        "extraction_cost_usd": round(sum(float(p.get("cost_usd") or 0.0) for p in ledger), 6),
    }
    repos.mark_document_ready(
        tenant_id,
        document_id,
        page_count=len(model.pages),
        model_key=model_key,
        ledger=ledger,
        domain_hint=_domain_hint(model),
        stats=stats,
    )
    logger.info("ready tenant=%s doc=%s pages=%d chunks=%d %.1fs", tenant_id, document_id, len(model.pages), result.chunk_count, total)
    return IngestResult(
        document_id=document_id,
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
    preview: bool = True,
) -> IngestResult:
    """Submit and process one PDF in this process (CLI, benchmark). Idempotent per file."""
    from src.db import repos

    submitted = submit_document(pdf_path, principal=principal, file_name=file_name, blobs=blobs, enqueue=False)
    if submitted.deduplicated:
        return submitted
    try:
        return process_document(
            principal.tenant_id,
            submitted.document_id,
            embedder=embedder,
            embed=embed,
            vision_client=vision_client,
            allow_vision=allow_vision,
            model=model,
            blobs=blobs,
            stores=stores,
            preview=preview,
        )
    except Exception as exc:
        logger.exception("ingest failed tenant=%s doc=%s", principal.tenant_id, submitted.document_id)
        repos.mark_document_failed(principal.tenant_id, submitted.document_id, f"{type(exc).__name__}: {exc}")
        raise
