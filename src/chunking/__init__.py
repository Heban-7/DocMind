"""Context-aware chunking: Markdown -> RAG-ready Logical Document Units (LDUs).

    from src.chunking.engine import ContextAwareChunker
    from src.chunking.models import DocumentChunk, ChunkMetadata
"""

from src.chunking.engine import (
    ChunkValidationError,
    ChunkValidator,
    ContextAwareChunker,
)
from src.chunking.models import ChunkMetadata, DocumentChunk, compute_content_hash

__all__ = [
    "ContextAwareChunker",
    "ChunkValidator",
    "ChunkValidationError",
    "DocumentChunk",
    "ChunkMetadata",
    "compute_content_hash",
]
