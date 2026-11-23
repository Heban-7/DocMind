"""API service helpers: upload ingest, chat and history, scoped to the caller.

Every function takes the caller's ``Principal``. Documents are reached
through the tenant's Postgres rows (row-level security), chat threads through
the ``threads`` table (one owner each), and conversation memory through a
checkpoint key that includes the tenant.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import UploadFile

from src.agents.memory import checkpoint_key, postgres_checkpointer, read_messages
from src.agents.query_agent import QueryAgent, build_query_agent
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    DocumentListResponse,
    HistoryMessage,
    HistoryResponse,
    ThreadListResponse,
    ThreadSummary,
    UploadResponse,
)
from src.db import repos
from src.db.repos import AccessDeniedError, DocumentRow, Principal, ThreadRow
from src.llm.factory import get_text_client
from src.models.intent import CorpusDocument
from src.pipeline.ingest import ingest_document
from src.storage.blobs import get_blob_store
from src.stores.pg import as_uuid, pg_stores

logger = logging.getLogger("docmind.api")

__all__ = ["AccessDeniedError"]


def _max_upload_bytes() -> int:
    return int(float(os.getenv("DOCMIND_MAX_UPLOAD_MB", "50")) * 1024 * 1024)


def _skip_embed() -> bool:
    return os.getenv("DOCMIND_API_SKIP_EMBED", "").lower() in {"1", "true", "yes"}


def _status_label(doc: DocumentRow | str) -> str:
    """The frontend's word for a ready document is still ``indexed``."""
    status = doc if isinstance(doc, str) else doc.status
    return "indexed" if status == "ready" else status


def _engines_label(engines: dict) -> str:
    return "page_level" if engines else "standard"


def _doc_info(doc: DocumentRow) -> DocumentInfo:
    return DocumentInfo(
        document_id=doc.id,
        file_name=doc.file_name,
        page_count=doc.page_count,
        strategy_tier=_engines_label((doc.stats or {}).get("engines") or {}),
        status=_status_label(doc),
        pages_needing_review=doc.pages_needing_review,
    )


# --- Upload ------------------------------------------------------------------


def _spool_upload(file: UploadFile, folder: Path) -> Path:
    """Copy the upload to a private temp file, enforcing type and size."""
    if not file.filename:
        raise ValueError("Uploaded file has no filename.")
    content_type = (file.content_type or "").lower()
    if not file.filename.lower().endswith(".pdf") and "pdf" not in content_type:
        raise ValueError("Only PDF uploads are supported.")
    target = folder / "upload.pdf"
    limit = _max_upload_bytes()
    written = 0
    with target.open("wb") as out:
        while True:
            block = file.file.read(1 << 20)
            if not block:
                break
            written += len(block)
            if written > limit:
                raise ValueError(f"PDF is larger than {limit // (1024 * 1024)} MB.")
            out.write(block)
    if written == 0:
        raise ValueError("Uploaded PDF is empty.")
    with target.open("rb") as fh:
        if fh.read(5) != b"%PDF-":
            raise ValueError("The file is not a PDF.")
    return target


def _display_name(name: str) -> str:
    base = Path(name or "upload.pdf").name.strip() or "upload.pdf"
    return base[:255]


def process_upload(file: UploadFile, *, principal: Principal) -> UploadResponse:
    """Store the PDF and index it for the caller's tenant."""
    folder = Path(tempfile.mkdtemp(prefix="docmind-upload-"))
    try:
        path = _spool_upload(file, folder)
        result = ingest_document(
            path,
            principal=principal,
            file_name=_display_name(file.filename or ""),
            embed=not _skip_embed(),
        )
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return UploadResponse(
        document_id=result.document_id,
        file_name=result.file_name,
        page_count=result.page_count,
        strategy_tier=_engines_label(result.engines or (result.stats or {}).get("engines") or {}),
        status=_status_label(result.status),
        pages_needing_review=result.pages_needing_review,
        deduplicated=result.deduplicated,
    )


# --- Documents ---------------------------------------------------------------


def list_documents(*, principal: Principal) -> DocumentListResponse:
    return DocumentListResponse(documents=[_doc_info(d) for d in repos.list_documents(principal.tenant_id)])


def get_pdf_file_path(doc_id: str, *, principal: Principal) -> Path:
    """Local path of the stored PDF of a document in the caller's tenant.

    Raises AccessDeniedError for documents of other tenants (and malformed
    ids), and FileNotFoundError when the stored file itself is missing.
    """
    doc = repos.require_document(principal.tenant_id, doc_id)
    try:
        return get_blob_store().local_path(doc.storage_key)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"PDF for document_id={doc_id} not found.") from exc


def _pdf_resolver(tenant_id: str):
    blobs = get_blob_store()

    def resolve(doc_id: str) -> Path | None:
        doc = repos.get_document(tenant_id, doc_id)
        if doc is None:
            return None
        try:
            return blobs.local_path(doc.storage_key)
        except FileNotFoundError:
            return None

    return resolve


def _corpus(tenant_id: str) -> list[CorpusDocument]:
    return [
        CorpusDocument(
            document_id=d.id,
            document_name=d.file_name,
            domain_hint=d.domain_hint,
            page_count=d.page_count,
        )
        for d in repos.list_documents(tenant_id, ready_only=True)
    ]


# --- Chat --------------------------------------------------------------------


def authorize_chat(payload: ChatRequest, *, principal: Principal) -> ThreadRow:
    """Check thread and document access before any work (or streaming) starts.

    The first user to write to a thread owns it; anyone else gets "not found".
    """
    if payload.document_id:
        repos.require_document(principal.tenant_id, payload.document_id)
    return repos.claim_thread(principal, payload.thread_id, payload.document_id)


def _agent_for_chat(principal: Principal, document_id: str | None, model: str | None) -> QueryAgent:
    llm_client = get_text_client(model=model) if model else None
    return build_query_agent(
        document_id,
        stores=pg_stores(principal.tenant_id),
        llm=llm_client,
        pdf_resolver=_pdf_resolver(principal.tenant_id),
        checkpointer=postgres_checkpointer(),
        corpus=_corpus(principal.tenant_id),
    )


def run_chat(payload: ChatRequest, *, principal: Principal) -> ChatResponse:
    """Invoke the LangGraph Query Agent and return answer + provenance."""
    thread = authorize_chat(payload, principal=principal)
    bound = thread.document_id
    if bound and repos.get_document(principal.tenant_id, bound) is None:
        bound = None
    doc_pin = None if payload.federated_search else (as_uuid(payload.document_id) or bound)

    agent = _agent_for_chat(principal, doc_pin, payload.model)
    if payload.audit_mode:
        logger.info("Chat invoked under audit mode thread_id=%s", payload.thread_id)
    answer = agent.ask(payload.message, thread_id=checkpoint_key(principal.tenant_id, payload.thread_id))
    repos.record_turn(principal, payload.thread_id, question=payload.message)

    provenance = []
    for c in answer.provenance.citations:
        d = c.model_dump(mode="json")
        if not d.get("doc_id") and doc_pin:
            d["doc_id"] = doc_pin
        provenance.append(d)

    return ChatResponse(
        response=answer.answer,
        thread_id=payload.thread_id,
        provenance=provenance,
        follow_ups=list(answer.follow_ups) if answer.follow_ups else [],
    )


def run_chat_stream(payload: ChatRequest, *, principal: Principal):
    """Stream response tokens followed by metadata JSON as Server-Sent Events."""
    res = run_chat(payload, principal=principal)
    words = res.response.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == len(words) - 1 else word + " "
        yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
        time.sleep(0.012)
    done_evt = {"type": "done", "provenance": res.provenance, "follow_ups": res.follow_ups}
    yield f"data: {json.dumps(done_evt)}\n\n"


# --- Threads and history -----------------------------------------------------


def _doc_info_or_none(tenant_id: str, doc_id: str | None) -> DocumentInfo | None:
    if not doc_id:
        return None
    doc = repos.get_document(tenant_id, doc_id)
    return _doc_info(doc) if doc else None


def fetch_history(thread_id: str, *, principal: Principal) -> HistoryResponse:
    """Load persisted conversation turns for one of the caller's threads."""
    tid = (thread_id or "").strip()
    if not tid:
        raise ValueError("thread_id must be a non-empty string.")
    thread = repos.get_thread(principal, tid)  # fail closed: others' threads are "not found"
    messages = [
        HistoryMessage(role=m.role.value, content=m.content)
        for m in read_messages(postgres_checkpointer(), checkpoint_key(principal.tenant_id, tid))
    ]
    return HistoryResponse(
        thread_id=tid,
        messages=messages,
        document_id=thread.document_id,
        document_info=_doc_info_or_none(principal.tenant_id, thread.document_id),
    )


def list_threads(*, principal: Principal) -> ThreadListResponse:
    """The caller's own threads, most recent first."""
    return ThreadListResponse(
        threads=[
            ThreadSummary(
                thread_id=t.id,
                title=t.title or "Conversation",
                message_count=t.message_count,
                document_id=t.document_id,
                document_info=_doc_info_or_none(principal.tenant_id, t.document_id),
            )
            for t in repos.list_threads(principal)
        ]
    )
