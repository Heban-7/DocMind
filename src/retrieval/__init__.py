"""Retrieval layer: OpenAI embeddings + Chroma LDU store.

    from src.retrieval import ingest_from_chunks_file, semantic_search
"""

from src.retrieval.embeddings import (
    EmbeddingClient,
    OpenAIEmbeddingClient,
    build_embedding_client,
)
from src.retrieval.ingest import (
    IngestResult,
    ingest_chunks,
    ingest_from_chunks_file,
    semantic_search,
)
from src.retrieval.vector_store import ChromaLDUStore, RetrievedChunk

__all__ = [
    "EmbeddingClient",
    "OpenAIEmbeddingClient",
    "build_embedding_client",
    "ChromaLDUStore",
    "RetrievedChunk",
    "IngestResult",
    "ingest_chunks",
    "ingest_from_chunks_file",
    "semantic_search",
]
