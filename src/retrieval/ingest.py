"""Embed chunks into a ChunkStore and search them.

Idempotent per document: a re-ingest replaces that document's chunks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.chunking.models import DocumentChunk
from src.retrieval.embeddings import EmbeddingClient, build_embedding_client
from src.stores.base import ChunkStore, RetrievedChunk

logger = logging.getLogger("docmind.retrieval")


@dataclass
class IngestResult:
    doc_id: str
    document_name: str
    chunks_ingested: int
    embedded: bool
    texts_embedded: int = 0  # new embeddings requested (the rest were reused)


def ingest_chunks(
    chunks: list[DocumentChunk],
    *,
    doc_id: str,
    store: ChunkStore,
    document_name: str = "",
    embedder: EmbeddingClient | None = None,
    embed: bool = True,
) -> IngestResult:
    """Embed (unless ``embed=False``) and store one document's chunks.

    Chunks whose exact text is already stored for this document keep their
    vector, so re-indexing (the quick preview, then the full read) only pays
    for text that changed.
    """
    vectors = None
    fresh = 0
    if embed and chunks:
        known = store.existing_embeddings(doc_id)
        todo = [c for c in chunks if c.metadata.content_hash not in known]
        if todo:
            embedder = embedder or build_embedding_client()
            for c, v in zip(todo, embedder.embed([c.text for c in todo])):
                known[c.metadata.content_hash] = v
            fresh = len(todo)
        vectors = [known[c.metadata.content_hash] for c in chunks]
    written = store.replace_doc_chunks(doc_id, chunks, vectors, document_name=document_name)
    logger.info("ingest doc_id=%s chunks=%d embedded=%s new=%d", doc_id, written, vectors is not None, fresh)
    return IngestResult(
        doc_id=doc_id,
        document_name=document_name or doc_id,
        chunks_ingested=written,
        embedded=vectors is not None,
        texts_embedded=fresh,
    )


def semantic_search(
    query: str,
    *,
    store: ChunkStore,
    doc_id: str | None = None,
    top_k: int = 7,
    embedder: EmbeddingClient | None = None,
) -> list[RetrievedChunk]:
    """Embed a query string and return the nearest chunks."""
    embedder = embedder or build_embedding_client()
    vector = embedder.embed([query])[0]
    return store.query(vector, doc_id=doc_id, top_k=top_k)
