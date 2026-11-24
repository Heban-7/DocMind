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
import queue
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from src.agents.memory import checkpoint_key, postgres_checkpointer, read_messages
from src.agents.prompt_profiles import normalize_mode
from src.agents.query_agent import QueryAgent, build_query_agent
from src.api.schemas import (
    AnswerUsage,
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
from src.llm import ledger, usage
from src.llm.errors import LLMError
from src.llm.factory import catalog, client_for_request
from src.models.intent import CorpusDocument
from src.pipeline.ingest import submit_document
from src.storage.blobs import get_blob_store
from src.stores.pg import as_uuid, pg_stores

logger = logging.getLogger("docmind.api")

__all__ = ["AccessDeniedError", "DocumentNotReadyError"]


class DocumentNotReadyError(RuntimeError):
    """The pinned document cannot be searched yet (still being read, or failed)."""


def _max_upload_bytes() -> int:
    return int(float(os.getenv("DOCMIND_MAX_UPLOAD_MB", "50")) * 1024 * 1024)


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
        stage=doc.stage,
        pages_done=doc.pages_done,
        progress=doc.progress,
        searchable=doc.searchable,
        error=doc.error if doc.status == "failed" else None,
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
    """Store the PDF and queue it for the worker; returns in milliseconds.

    Follow progress with ``GET /documents/{id}`` or ``/documents/{id}/events``.
    Raises SpendingCapError when the account's monthly model budget is used
    up (reading a document embeds it, and may call a vision model).
    """
    folder = Path(tempfile.mkdtemp(prefix="docmind-upload-"))
    try:
        path = _spool_upload(file, folder)  # rejects what is not a PDF first
        ledger.check_caps(principal.tenant_id)
        result = submit_document(path, principal=principal, file_name=_display_name(file.filename or ""))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    doc = repos.require_document(principal.tenant_id, result.document_id)
    info = _doc_info(doc)
    return UploadResponse(
        document_id=info.document_id,
        file_name=info.file_name,
        page_count=info.page_count,
        strategy_tier=info.strategy_tier,
        status=info.status,
        pages_needing_review=info.pages_needing_review,
        deduplicated=result.deduplicated,
        stage=info.stage,
        pages_done=info.pages_done,
        progress=info.progress,
        searchable=info.searchable,
    )


# --- Documents ---------------------------------------------------------------


def list_documents(*, principal: Principal) -> DocumentListResponse:
    return DocumentListResponse(documents=[_doc_info(d) for d in repos.list_documents(principal.tenant_id)])


def get_document_status(doc_id: str, *, principal: Principal) -> DocumentInfo:
    return _doc_info(repos.require_document(principal.tenant_id, doc_id))


def document_events(doc_id: str, *, principal: Principal, interval: float = 1.0, timeout: float = 3600.0):
    """Server-Sent Events with the document's progress until it is ready or failed."""
    repos.require_document(principal.tenant_id, doc_id)  # fail before the stream starts
    deadline = time.monotonic() + timeout
    last = None
    while True:
        info = get_document_status(doc_id, principal=principal)
        payload = info.model_dump(mode="json")
        if payload != last:
            yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
            last = payload
        if info.status in ("indexed", "failed") or time.monotonic() > deadline:
            yield f"event: end\ndata: {json.dumps({'status': info.status})}\n\n"
            return
        time.sleep(interval)


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


def authorize_chat(payload: ChatRequest, *, principal: Principal) -> tuple[ThreadRow, str | None]:
    """Check thread and document access before any work (or streaming) starts.

    The first user to write to a thread owns it; anyone else gets "not found".
    Returns the thread and the document the answer is pinned to (None for a
    search across all documents). A pinned document that cannot be searched
    yet raises DocumentNotReadyError.
    """
    if payload.document_id:
        repos.require_document(principal.tenant_id, payload.document_id)
    thread = repos.claim_thread(principal, payload.thread_id, payload.document_id)
    bound = thread.document_id
    if bound and repos.get_document(principal.tenant_id, bound) is None:
        bound = None
    doc_pin = None if payload.federated_search else (as_uuid(payload.document_id) or bound)
    if doc_pin:
        pinned = repos.require_document(principal.tenant_id, doc_pin)
        if not pinned.searchable:
            state = (
                "failed to process" if pinned.status == "failed"
                else f"still being read ({pinned.pages_done} of {pinned.page_count} pages)"
            )
            raise DocumentNotReadyError(f"{pinned.file_name} is {state}.")
    return thread, doc_pin


def _agent_for_chat(principal: Principal, document_id: str | None, model: str | None, mode: str) -> QueryAgent:
    # the model a user picked must be the model that answers (no silent switch)
    llm_client = client_for_request(model)
    return build_query_agent(
        document_id,
        stores=pg_stores(principal.tenant_id),
        llm=llm_client,
        pdf_resolver=_pdf_resolver(principal.tenant_id),
        checkpointer=postgres_checkpointer(),
        corpus=_corpus(principal.tenant_id),
        mode=mode,
    )


@dataclass
class PreparedChat:
    agent: QueryAgent
    doc_pin: str | None
    mode: str


def prepare_chat(payload: ChatRequest, *, principal: Principal) -> PreparedChat:
    """Everything that can fail with a clear status code, before any work or streaming starts.

    Raises AccessDeniedError, DocumentNotReadyError, ModelNotAvailableError,
    SpendingCapError or RuntimeError (no model configured).
    """
    _thread, doc_pin = authorize_chat(payload, principal=principal)
    ledger.check_caps(principal.tenant_id)
    mode = normalize_mode(payload.mode, audit=payload.audit_mode)
    return PreparedChat(agent=_agent_for_chat(principal, doc_pin, payload.model, mode), doc_pin=doc_pin, mode=mode)


def _provenance(answer, doc_pin: str | None) -> list[dict]:
    out = []
    for c in answer.provenance.citations:
        d = c.model_dump(mode="json")
        if not d.get("doc_id") and doc_pin:
            d["doc_id"] = doc_pin
        out.append(d)
    return out


def _answer_usage(answer, agent: QueryAgent) -> AnswerUsage:
    u, t = answer.usage or {}, answer.timings or {}
    return AnswerUsage(
        model=agent.deps.llm.model,
        provider=agent.deps.llm.provider,
        llm_calls=int(u.get("llm_calls") or 0),
        input_tokens=int(u.get("input_tokens") or 0),
        output_tokens=int(u.get("output_tokens") or 0),
        cost_usd=float(u.get("cost_usd") or 0.0),
        seconds=float(t.get("total_s") or 0.0),
        first_token_s=t.get("first_token_s"),
    )


def _chat_response(payload: ChatRequest, prepared: PreparedChat, answer) -> ChatResponse:
    return ChatResponse(
        response=answer.answer,
        thread_id=payload.thread_id,
        provenance=_provenance(answer, prepared.doc_pin),
        follow_ups=list(answer.follow_ups or []),
        status=answer.status,
        mode=answer.mode,
        prompt_profile=answer.prompt_profile,
        usage=_answer_usage(answer, prepared.agent),
        verification={k: v for k, v in (answer.verification or {}).items()},
    )


def _ask(payload: ChatRequest, prepared: PreparedChat, principal: Principal, on_token=None):
    """Run the agent and write its model calls to the ledger, whatever the outcome."""
    with usage.collect() as events:
        try:
            return prepared.agent.ask(
                payload.message,
                thread_id=checkpoint_key(principal.tenant_id, payload.thread_id),
                on_token=on_token,
                mode=prepared.mode,
            )
        finally:
            ledger.record(
                events,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                thread_id=payload.thread_id,
                document_id=prepared.doc_pin,
            )


def run_chat(payload: ChatRequest, *, principal: Principal, prepared: PreparedChat | None = None) -> ChatResponse:
    """Answer one message; raises LLMError when the model provider fails."""
    prepared = prepared or prepare_chat(payload, principal=principal)
    answer = _ask(payload, prepared, principal)
    repos.record_turn(principal, payload.thread_id, question=payload.message)
    return _chat_response(payload, prepared, answer)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def run_chat_stream(payload: ChatRequest, *, principal: Principal, prepared: PreparedChat):
    """Server-Sent Events: the answer's text as the model writes it, then the checked answer.

    Events: {"type": "token", "token": "..."} while the answer is written;
    then {"type": "done", "answer": <the verified text, which replaces the
    streamed text>, "provenance", "follow_ups", "status", "usage",
    "verification"}; or {"type": "error", "kind", "message"} when the model
    provider fails (the answer is then not saved as "not found").
    """
    pieces: queue.Queue = queue.Queue()
    _END = object()

    def work() -> None:
        try:
            answer = _ask(payload, prepared, principal, on_token=lambda t: pieces.put(("token", t)))
            repos.record_turn(principal, payload.thread_id, question=payload.message)
            pieces.put(("done", _chat_response(payload, prepared, answer)))
        except LLMError as exc:
            logger.warning("chat stream: model error %s (%s)", exc.kind, exc)
            pieces.put(("error", {"kind": exc.kind, "message": exc.user_message()}))
        except Exception as exc:  # pragma: no cover - surfaced to the client as an error event
            logger.exception("chat stream failed thread_id=%s", payload.thread_id)
            pieces.put(("error", {"kind": "internal", "message": f"The answer failed: {type(exc).__name__}"}))
        finally:
            pieces.put((_END, None))

    threading.Thread(target=usage.run_in_context(work), daemon=True).start()
    while True:
        kind, value = pieces.get()
        if kind is _END:
            return
        if kind == "token":
            yield _sse({"type": "token", "token": value})
        elif kind == "done":
            res: ChatResponse = value
            yield _sse(
                {
                    "type": "done",
                    "answer": res.response,
                    "provenance": res.provenance,
                    "follow_ups": res.follow_ups,
                    "status": res.status,
                    "mode": res.mode,
                    "usage": res.usage.model_dump(),
                    "verification": {k: v for k, v in res.verification.items() if k != "sentences"},
                }
            )
        else:
            yield _sse({"type": "error", **value})


def model_catalog() -> dict:
    return catalog()


def usage_report(*, principal: Principal) -> dict:
    return ledger.usage_summary(principal.tenant_id)


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
