"""
Ingest Phase 3 LDUs into Chroma via OpenAI embeddings.

Idempotent per ``doc_id``: delete existing vectors for that doc, then upsert
fresh ones. This is the bridge from chunking output to ``semantic_search``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.chunking.models import DocumentChunk
from src.config import CHUNKS_DIR
from src.pageindex.builder import load_chunks_jsonl
from src.retrieval.embeddings import EmbeddingClient, build_embedding_client
from src.retrieval.vector_store import ChromaLDUStore

logger = logging.getLogger("docmind.retrieval")


@dataclass
class IngestResult:
    doc_id: str
    document_name: str
    chunks_ingested: int
    collection_total: int


def ingest_chunks(
    chunks: list[DocumentChunk],
    *,
    doc_id: str,
    document_name: str = "",
    store: ChromaLDUStore | None = None,
    embedder: EmbeddingClient | None = None,
) -> IngestResult:
    """Embed and upsert LDUs for one document (replaces prior vectors for doc_id)."""
    store = store or ChromaLDUStore()
    embedder = embedder or build_embedding_client()

    store.delete_doc(doc_id)
    if not chunks:
        return IngestResult(
            doc_id=doc_id,
            document_name=document_name,
            chunks_ingested=0,
            collection_total=store.count,
        )

    texts = [c.text for c in chunks]
    vectors = embedder.embed(texts)
    written = store.upsert_chunks(
        doc_id=doc_id,
        document_name=document_name or doc_id,
        chunks=chunks,
        embeddings=vectors,
    )
    logger.info(
        "ingest doc_id=%s chunks=%d collection_total=%d",
        doc_id,
        written,
        store.count,
    )
    return IngestResult(
        doc_id=doc_id,
        document_name=document_name or doc_id,
        chunks_ingested=written,
        collection_total=store.count,
    )


def ingest_from_chunks_file(
    doc_id: str,
    *,
    document_name: str = "",
    chunks_dir: Path | None = None,
    store: ChromaLDUStore | None = None,
    embedder: EmbeddingClient | None = None,
) -> IngestResult:
    """Load ``.refinery/chunks/{doc_id}.jsonl`` and ingest into Chroma."""
    path = (chunks_dir or CHUNKS_DIR) / f"{doc_id}.jsonl"
    chunks = load_chunks_jsonl(path)
    return ingest_chunks(
        chunks,
        doc_id=doc_id,
        document_name=document_name,
        store=store,
        embedder=embedder,
    )


def semantic_search(
    query: str,
    *,
    doc_id: str | None = None,
    top_k: int = 7,
    store: ChromaLDUStore | None = None,
    embedder: EmbeddingClient | None = None,
):
    """Embed a query string and return the nearest LDUs (tool-ready helper)."""
    store = store or ChromaLDUStore()
    embedder = embedder or build_embedding_client()
    vector = embedder.embed([query])[0]
    return store.query(vector, doc_id=doc_id, top_k=top_k)
