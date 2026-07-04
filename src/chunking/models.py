"""
Typed, immutable contracts for the Chunking stage (Phase 3).

A `DocumentChunk` is a Logical Document Unit (LDU): a semantically coherent,
self-contained slice of the document that still remembers WHERE it came from
(its heading breadcrumb and source pages) and carries a cryptographic fingerprint
of its exact text for provenance/auditing.

These models are frozen (immutable) so a chunk cannot be silently mutated after
it has been validated and hashed -- the hash would no longer match its text.
"""

from __future__ import annotations

import hashlib
import uuid

from pydantic import BaseModel, ConfigDict, Field


def compute_content_hash(text: str) -> str:
    """SHA-256 hex digest of the exact chunk text (UTF-8).

    Same text in -> same hash out. This is the provenance anchor: if a page
    reflows or a re-extraction shifts layout, an unchanged chunk keeps the same
    hash, and any change to the text is detectable as a hash mismatch.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ChunkMetadata(BaseModel):
    """Structured provenance + routing metadata stamped on every chunk."""

    model_config = ConfigDict(frozen=True)

    parent_hierarchy: list[str] = Field(
        default_factory=list,
        description="Breadcrumb of headings above this text, e.g. "
        "['Chapter 1', 'Section A'].",
    )
    page_numbers: list[int] = Field(
        default_factory=lambda: [1],
        description="Physical source page indices this chunk spans.",
    )
    content_hash: str = Field(description="SHA-256 hex digest of the chunk text.")

    # --- Enrichment (useful for RAG routing/validation; safe defaults) -------
    chunk_type: str = Field(
        default="prose",
        description="prose | table | list | code | blockquote | heading | mixed",
    )
    word_count: int = Field(default=0, ge=0)


class DocumentChunk(BaseModel):
    """One Logical Document Unit: cleaned text + embedded provenance metadata."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    metadata: ChunkMetadata

    @classmethod
    def create(
        cls,
        text: str,
        *,
        parent_hierarchy: list[str],
        page_numbers: list[int] | None = None,
        chunk_type: str = "prose",
    ) -> DocumentChunk:
        """Build a chunk, auto-computing the content hash and word count."""
        metadata = ChunkMetadata(
            parent_hierarchy=list(parent_hierarchy),
            page_numbers=list(page_numbers) if page_numbers else [1],
            content_hash=compute_content_hash(text),
            chunk_type=chunk_type,
            word_count=len(text.split()),
        )
        return cls(text=text, metadata=metadata)
