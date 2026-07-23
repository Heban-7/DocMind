"""
ChromaDB wrapper for Logical Document Units (LDUs).

One persistent collection holds all ingested docs; queries filter by ``doc_id``
when scoped. Metadata is flat (Chroma requirement): hierarchy and page lists
are stored as delimited strings and re-parsed on read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.chunking.models import DocumentChunk
from src.config import CHROMA_DIR, EmbeddingConfig


def _pages_to_meta(pages: list[int]) -> str:
    return ",".join(str(p) for p in pages)


def _pages_from_meta(raw: str) -> list[int]:
    if not raw:
        return [1]
    return [int(p) for p in raw.split(",") if p.strip()]


def _hierarchy_to_meta(path: list[str]) -> str:
    # Use a rare delimiter so titles with " > " still round-trip poorly but
    # titles with "|" are uncommon; we also keep a JSON-safe join fallback.
    return " || ".join(path)


def _hierarchy_from_meta(raw: str) -> list[str]:
    if not raw:
        return []
    return [part for part in raw.split(" || ") if part]


@dataclass
class RetrievedChunk:
    """One semantic-search hit with score and provenance fields."""

    chunk_id: str
    text: str
    doc_id: str
    document_name: str
    page_numbers: list[int]
    parent_hierarchy: list[str]
    content_hash: str
    chunk_type: str
    distance: float  # lower = closer in Chroma's default L2 / cosine space

    @property
    def score(self) -> float:
        """Similarity-ish score in (0, 1]: 1 / (1 + distance)."""
        return 1.0 / (1.0 + max(self.distance, 0.0))


class ChromaLDUStore:
    """Persistent Chroma collection for DocMind LDUs."""

    def __init__(
        self,
        persist_dir: Path | str | None = None,
        collection_name: str | None = None,
    ):
        import chromadb
        from chromadb.config import Settings

        self.persist_dir = Path(persist_dir or CHROMA_DIR)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name or EmbeddingConfig.COLLECTION_NAME

        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    def delete_doc(self, doc_id: str) -> None:
        """Remove every LDU for a document (idempotent re-ingest prelude)."""
        existing = self._collection.get(where={"doc_id": doc_id})
        ids = existing.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)

    def upsert_chunks(
        self,
        *,
        doc_id: str,
        document_name: str,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Upsert LDUs with precomputed embeddings. Returns number written."""
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) "
                "length mismatch"
            )
        if not chunks:
            return 0

        ids = [c.id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [
            {
                "doc_id": doc_id,
                "document_name": document_name,
                "page_numbers": _pages_to_meta(c.metadata.page_numbers),
                "parent_hierarchy": _hierarchy_to_meta(c.metadata.parent_hierarchy),
                "content_hash": c.metadata.content_hash,
                "chunk_type": c.metadata.chunk_type,
                "word_count": c.metadata.word_count,
            }
            for c in chunks
        ]
        self._collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return len(ids)

    def query(
        self,
        query_embedding: list[float],
        *,
        doc_id: str | None = None,
        top_k: int = 7,
    ) -> list[RetrievedChunk]:
        """Nearest-neighbor search; optionally scoped to one document."""
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if doc_id:
            kwargs["where"] = {"doc_id": doc_id}

        raw = self._collection.query(**kwargs)
        ids = (raw.get("ids") or [[]])[0]
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        hits: list[RetrievedChunk] = []
        for i, chunk_id in enumerate(ids):
            meta = metas[i] or {}
            hits.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=docs[i] or "",
                    doc_id=str(meta.get("doc_id", "")),
                    document_name=str(meta.get("document_name", "")),
                    page_numbers=_pages_from_meta(str(meta.get("page_numbers", ""))),
                    parent_hierarchy=_hierarchy_from_meta(
                        str(meta.get("parent_hierarchy", ""))
                    ),
                    content_hash=str(meta.get("content_hash", "")),
                    chunk_type=str(meta.get("chunk_type", "prose")),
                    distance=float(dists[i] if i < len(dists) else 0.0),
                )
            )
        return hits
