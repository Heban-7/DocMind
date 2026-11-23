"""Storage interfaces used by retrieval tools, with Postgres and in-memory implementations.

The query tools depend only on these small interfaces. Production uses the
Postgres stores in ``src.stores.pg`` (tenant-scoped through row-level
security); unit tests and the offline demo use the in-memory ones.
"""

from src.stores.base import ChunkStore, FactStore, PageIndexStore, RetrievedChunk, Stores
from src.stores.memory import MemoryChunkStore, MemoryFactStore, MemoryPageIndexStore, memory_stores

__all__ = [
    "ChunkStore",
    "FactStore",
    "MemoryChunkStore",
    "MemoryFactStore",
    "MemoryPageIndexStore",
    "PageIndexStore",
    "RetrievedChunk",
    "Stores",
    "memory_stores",
]
