"""API service helpers: upload ingest + chat / history against the Query Agent."""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from src.agents.query_agent import QueryAgent, build_query_agent
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    HistoryMessage,
    HistoryResponse,
    UploadResponse,
)
from src.config import RAW_DIR
from src.pipeline.ingest import ingest_pdf
from src.pipeline.phase4 import resolve_pdf_path

logger = logging.getLogger("docmind.api")

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    base = Path(name or "upload.pdf").name
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "upload.pdf"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned


def save_upload(file: UploadFile, *, destination_dir: Path | None = None) -> Path:
    """Persist an uploaded PDF under ``data/raw/`` with a collision-safe name."""
    if not file.filename:
        raise ValueError("Uploaded file has no filename.")
    lowered = file.filename.lower()
    content_type = (file.content_type or "").lower()
    if not lowered.endswith(".pdf") and "pdf" not in content_type:
        raise ValueError("Only PDF uploads are supported.")

    dest_dir = destination_dir or RAW_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(file.filename)
    target = dest_dir / f"{uuid4().hex[:10]}_{safe}"

    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    if target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise ValueError("Uploaded PDF is empty.")
    return target


def process_upload(
    file: UploadFile,
    *,
    skip_embed: bool | None = None,
) -> UploadResponse:
    """Save PDF, run Phases 1-4 indexing, return an UploadResponse."""
    if skip_embed is None:
        skip_embed = os.getenv("DOCMIND_API_SKIP_EMBED", "").lower() in {
            "1",
            "true",
            "yes",
        }

    saved = save_upload(file)
    logger.info("upload saved path=%s", saved)
    try:
        result = ingest_pdf(saved, skip_phase4=False, skip_embed=skip_embed)
    except Exception:
        # Keep the raw file for debugging; re-raise for HTTP mapping.
        logger.exception("ingest failed for %s", saved)
        raise

    profile = result.profile
    status = "indexed" if result.phase4 is not None else "chunked"
    if result.phase4 is not None and skip_embed:
        status = "indexed_no_embed"

    return UploadResponse(
        document_id=profile.doc_id,
        file_name=profile.source_filename,
        page_count=profile.page_count,
        strategy_tier=profile.strategy_tier.value,
        status=status,
    )


def _agent_for_chat(document_id: str | None) -> QueryAgent:
    """Build a memory-backed Query Agent, optionally pinned to one document."""
    pdf_path = resolve_pdf_path(document_id) if document_id else None
    return build_query_agent(
        document_id,
        pdf_path=pdf_path,
        enable_memory=True,
    )


def run_chat(payload: ChatRequest) -> ChatResponse:
    """Invoke the LangGraph Query Agent and return answer + provenance."""
    agent = _agent_for_chat(payload.document_id)
    answer = agent.ask(payload.message, thread_id=payload.thread_id)
    provenance = [
        c.model_dump(mode="json") for c in answer.provenance.citations
    ]
    return ChatResponse(
        response=answer.answer,
        thread_id=payload.thread_id,
        provenance=provenance,
    )


def fetch_history(thread_id: str) -> HistoryResponse:
    """Load persisted conversation turns for ``thread_id``."""
    tid = (thread_id or "").strip()
    if not tid:
        raise ValueError("thread_id must be a non-empty string.")
    agent = build_query_agent(None, enable_memory=True)
    messages = [
        HistoryMessage(role=m.role.value, content=m.content)
        for m in agent.get_messages(tid)
    ]
    return HistoryResponse(thread_id=tid, messages=messages)
