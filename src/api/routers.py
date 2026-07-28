"""HTTP routers for the DocMind API gateway."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    HistoryResponse,
    UploadResponse,
)
from src.api.services import fetch_history, process_upload, run_chat

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
    status_code=status.HTTP_201_CREATED,
)
async def upload_pdf(file: UploadFile = File(...)) -> UploadResponse:
    """Accept a PDF, run Triage ? Extract ? Chunk ? Index, return the profile."""
    try:
        return process_upload(file)
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


@chat_router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    """Ask the Query Agent (memory via thread_id; optional document pin)."""
    try:
        return run_chat(payload)
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


@chat_router.get("/history/{thread_id}", response_model=HistoryResponse)
def history(thread_id: str) -> HistoryResponse:
    """Return prior turns for a conversation thread from the checkpointer."""
    try:
        return fetch_history(thread_id)
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
