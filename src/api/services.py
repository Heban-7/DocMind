"""API service helpers: upload ingest + chat / history against the Query Agent."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

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
from src.config import CHECKPOINTS_DB_PATH, PROFILES_DIR, RAW_DIR
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


def _agent_for_chat(document_id: str | None, model: str | None = None) -> QueryAgent:
    """Build a memory-backed Query Agent, optionally pinned to one document and model."""
    pdf_path = resolve_pdf_path(document_id) if document_id else None
    llm_client = get_text_client(model=model) if model else None
    return build_query_agent(
        document_id,
        pdf_path=pdf_path,
        llm=llm_client,
        enable_memory=True,
    )


def run_chat(payload: ChatRequest) -> ChatResponse:
    """Invoke the LangGraph Query Agent and return answer + provenance."""
    doc_pin = None if payload.federated_search else payload.document_id
    agent = _agent_for_chat(doc_pin, model=payload.model)
    if payload.audit_mode:
        logger.info("Chat invoked under Zero-Trust Audit Mode for thread_id=%s", payload.thread_id)
    if payload.model:
        logger.info("Chat requested model=%s for thread_id=%s", payload.model, payload.thread_id)
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


def list_threads() -> ThreadListResponse:
    """Return all active thread_ids with their titles and message counts."""
    if not CHECKPOINTS_DB_PATH.exists():
        return ThreadListResponse(threads=[])

    try:
        conn = sqlite3.connect(str(CHECKPOINTS_DB_PATH))
        cursor = conn.execute("SELECT DISTINCT thread_id FROM checkpoints")
        thread_ids = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()
    except Exception:
        logger.exception("Failed to query checkpoints DB")
        return ThreadListResponse(threads=[])

    agent = build_query_agent(None, enable_memory=True)
    summaries: list[ThreadSummary] = []
    for tid in thread_ids:
        msgs = agent.get_messages(tid)
        if not msgs:
            continue
        user_msgs = [m for m in msgs if m.role.value == "user"]
        first_text = user_msgs[0].content if user_msgs else "Conversation"
        title = first_text[:60] + ("..." if len(first_text) > 60 else "")
        summaries.append(
            ThreadSummary(
                thread_id=tid,
                title=title,
                message_count=len(msgs),
            )
        )
    return ThreadListResponse(threads=summaries)


def list_documents() -> DocumentListResponse:
    """Return all ingested document profiles from PROFILES_DIR."""
    if not PROFILES_DIR.exists():
        return DocumentListResponse(documents=[])

    docs: list[DocumentInfo] = []
    for p in PROFILES_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            docs.append(
                DocumentInfo(
                    document_id=data.get("doc_id", p.stem),
                    file_name=data.get("source_filename", p.name),
                    page_count=data.get("page_count", 0),
                    strategy_tier=data.get("estimated_cost", {}).get("value", "standard")
                    if isinstance(data.get("estimated_cost"), dict)
                    else str(data.get("estimated_cost", "standard")),
                    status="indexed",
                )
            )
        except Exception:
            continue

    return DocumentListResponse(documents=docs)


def get_pdf_file_path(doc_id: str) -> Path:
    """Resolve PDF file path for a document_id or raise FileNotFoundError."""
    path = resolve_pdf_path(doc_id)
    if path is None or not path.exists():
        raise FileNotFoundError(f"PDF for document_id={doc_id} not found.")
    return path
