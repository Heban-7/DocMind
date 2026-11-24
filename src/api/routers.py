"""HTTP routers for the DocMind API gateway."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from src.api.dependencies import get_principal, get_principal_header_or_query
from src.db.repos import AccessDeniedError, Principal

from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    DocumentListResponse,
    HealthResponse,
    HistoryResponse,
    ThreadListResponse,
    UploadResponse,
)
from src.api.services import (
    DocumentNotReadyError,
    document_events,
    fetch_history,
    get_document_status,
    get_pdf_file_path,
    list_documents,
    list_threads,
    process_upload,
    run_chat,
)

logger = logging.getLogger("docmind.api")

API_VERSION = "0.1.0"

health_router = APIRouter(tags=["health"])
upload_router = APIRouter(tags=["documents"])
chat_router = APIRouter(tags=["chat"])


@health_router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness / readiness probe for load balancers and local frontend."""
    return HealthResponse(status="ok", version=API_VERSION)


@upload_router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_pdf(
    file: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
) -> UploadResponse:
    """Store a PDF and queue it; the worker reads it in the background.

    A plain ``def`` on purpose: FastAPI runs it in a worker thread, so a slow
    disk never blocks the event loop (and with it every other request).
    """
    try:
        return process_upload(file, principal=principal)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("upload pipeline failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document processing failed: {exc}",
        ) from exc


@upload_router.get("/documents", response_model=DocumentListResponse)
def get_documents(principal: Principal = Depends(get_principal)) -> DocumentListResponse:
    """List the documents in the caller's account."""
    try:
        return list_documents(principal=principal)
    except Exception as exc:
        logger.exception("list documents failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {exc}",
        ) from exc


@upload_router.get("/documents/{doc_id}", response_model=DocumentInfo)
def get_document(doc_id: str, principal: Principal = Depends(get_principal)) -> DocumentInfo:
    """Status and progress of one document (queued, processing, indexed, failed)."""
    try:
        return get_document_status(doc_id, principal=principal)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc


@upload_router.get("/documents/{doc_id}/events")
def get_document_events(doc_id: str, principal: Principal = Depends(get_principal_header_or_query)):
    """Server-Sent Events with progress until the document is ready or failed.

    Accepts ``?token=`` because a browser EventSource cannot send headers.
    """
    from starlette.responses import StreamingResponse

    try:
        stream = document_events(doc_id, principal=principal)
        first = next(stream)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc

    def gen():
        yield first
        yield from stream

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@upload_router.get("/documents/{doc_id}/pdf")
def get_pdf(
    doc_id: str,
    principal: Principal = Depends(get_principal_header_or_query),
):
    """Serve the stored PDF of a document in the caller's account.

    Login is required. The token may come from the Authorization header or,
    for the in-browser viewer, a ``token`` query parameter (to be replaced by
    short-lived signed URLs in milestone M9). Documents the caller does not own
    return 404, exactly like documents that do not exist.
    """
    try:
        pdf_path = get_pdf_file_path(doc_id, principal=principal)
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            content_disposition_type="inline",
        )
    except AccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("pdf fetch failed doc_id=%s", doc_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve PDF: {exc}",
        ) from exc


@chat_router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, principal: Principal = Depends(get_principal)) -> ChatResponse:
    """Ask the Query Agent (memory via thread_id; optional document pin)."""
    try:
        return run_chat(payload, principal=principal)
    except AccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread or document not found.",
        ) from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Missing LLM keys / misconfigured providers.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("chat failed thread_id=%s", payload.thread_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {exc}",
        ) from exc


@chat_router.post("/chat/stream")
def chat_stream(payload: ChatRequest, principal: Principal = Depends(get_principal)):
    """Stream Query Agent response token by token via Server-Sent Events."""
    from starlette.responses import StreamingResponse
    from src.api.services import authorize_chat, run_chat_stream

    # Access is checked before the stream starts: once a 200 and the SSE
    # headers are sent, an error can no longer become a proper status code.
    try:
        authorize_chat(payload, principal=principal)
    except AccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread or document not found.",
        ) from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        return StreamingResponse(
            run_chat_stream(payload, principal=principal),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    except Exception as exc:
        logger.exception("chat_stream failed thread_id=%s", payload.thread_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat stream failed: {exc}",
        ) from exc


@chat_router.get("/history/{thread_id}", response_model=HistoryResponse)
def history(thread_id: str, principal: Principal = Depends(get_principal)) -> HistoryResponse:
    """Return prior turns for one of the caller's conversation threads."""
    try:
        return fetch_history(thread_id, principal=principal)
    except AccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("history failed thread_id=%s", thread_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"History lookup failed: {exc}",
        ) from exc


@chat_router.get("/threads", response_model=ThreadListResponse)
def get_threads(principal: Principal = Depends(get_principal)) -> ThreadListResponse:
    """List the caller's conversation threads, most recent first."""
    try:
        return list_threads(principal=principal)
    except Exception as exc:
        logger.exception("list threads failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list threads: {exc}",
        ) from exc

