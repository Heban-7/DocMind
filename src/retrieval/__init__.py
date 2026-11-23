"""Retrieval layer: embeddings and chunk search over a ChunkStore.

    from src.retrieval import ingest_chunks, semantic_search
"""

from src.retrieval.embeddings import (
    EmbeddingClient,
    OpenAIEmbeddingClient,
    build_embedding_client,
)
from src.retrieval.ingest import IngestResult, ingest_chunks, semantic_search
from src.stores.base import RetrievedChunk

__all__ = [
    "EmbeddingClient",
    "OpenAIEmbeddingClient",
    "build_embedding_client",
    "RetrievedChunk",
    "IngestResult",
    "ingest_chunks",
    "semantic_search",
]
