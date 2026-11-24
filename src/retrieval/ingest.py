"""Embed chunks into a ChunkStore, and search them (hybrid + rerank).

Each chunk is embedded together with its context, the document's title and
its section path ("CBE Annual Report 2023-24 > Financial statements >
Note 23"), so a table that never names its subject still matches a question
about it. Idempotent per document: a re-ingest replaces that document's
chunks, and a vector is reused when the exact embedded text is unchanged.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path

from src.chunking.models import DocumentChunk
from src.retrieval.embeddings import EmbeddingClient, build_embedding_client
from src.stores.base import ChunkStore, RetrievedChunk

logger = logging.getLogger("docmind.retrieval")


def document_title(document_name: str) -> str:
    """'CBE ANNUAL REPORT 2023-24.pdf' -> 'CBE ANNUAL REPORT 2023-24'"""
    stem = Path(document_name or "").stem
    return re.sub(r"[_]+", " ", stem).strip()


def chunk_context(chunk: DocumentChunk, document_name: str) -> str:
    parts = [document_title(document_name), *chunk.metadata.parent_hierarchy]
    return " > ".join(p for p in parts if p)[:500]


def embed_text(chunk: DocumentChunk, context: str) -> str:
    return f"{context}\n\n{chunk.text}" if context else chunk.text


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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

    Chunks whose embedded text (context + text) is already stored for this
    document keep their vector, so re-indexing (the quick preview, then the
    full read) only pays for text that changed.
    """
    contexts = [chunk_context(c, document_name) for c in chunks]
    texts = [embed_text(c, ctx) for c, ctx in zip(chunks, contexts)]
    hashes = [_hash(t) for t in texts]
    vectors = None
    fresh = 0
    if embed and chunks:
        known = store.existing_embeddings(doc_id)
        todo = [i for i, h in enumerate(hashes) if h not in known]
        if todo:
            embedder = embedder or build_embedding_client()
            for i, v in zip(todo, embedder.embed([texts[i] for i in todo])):
                known[hashes[i]] = v
            fresh = len(todo)
        vectors = [known[h] for h in hashes]
    written = store.replace_doc_chunks(
        doc_id, chunks, vectors, document_name=document_name, contexts=contexts, embed_hashes=hashes
    )
    logger.info("ingest doc_id=%s chunks=%d embedded=%s new=%d", doc_id, written, vectors is not None, fresh)
    return IngestResult(
        doc_id=doc_id,
        document_name=document_name or doc_id,
        chunks_ingested=written,
        embedded=vectors is not None,
        texts_embedded=fresh,
    )


def retrieve(
    query: str,
    *,
    store: ChunkStore,
    doc_id: str | None = None,
    top_k: int = 7,
    candidates: int = 20,
    embedder: EmbeddingClient | None = None,
    rerank: bool = True,
) -> list[RetrievedChunk]:
    """Hybrid search (vectors + keywords, fused), then the cross-encoder reranks the candidates."""
    from src.retrieval import rerank as reranker

    from src.llm.errors import LLMError

    embedder = embedder or build_embedding_client()
    try:
        vector = embedder.embed([query])[0]
    except LLMError as exc:
        if exc.kind == "deadline":
            raise
        # keyword search still works without the embedding provider
        logger.warning("Embedding the query failed (%s); searching by keywords only", exc.kind)
        vector = None
    found = store.search(query, vector, doc_id=doc_id, top_k=max(top_k, candidates))
    if rerank and len(found) > 1:
        scores = reranker.scores(query, [embed_text_for_hit(h) for h in found])
        if scores is not None:
            ranked = sorted(zip(scores, range(len(found)), found), key=lambda t: (-t[0], t[1]))
            found = [replace(h, relevance=round(s, 4)) for s, _, h in ranked]
    return found[:top_k]


def embed_text_for_hit(hit: RetrievedChunk) -> str:
    return f"{hit.context}\n{hit.text}" if hit.context else hit.text


def semantic_search(
    query: str,
    *,
    store: ChunkStore,
    doc_id: str | None = None,
    top_k: int = 7,
    embedder: EmbeddingClient | None = None,
) -> list[RetrievedChunk]:
    """The retrieval the agent uses: hybrid search and reranking (see ``retrieve``)."""
    return retrieve(query, store=store, doc_id=doc_id, top_k=top_k, embedder=embedder)
