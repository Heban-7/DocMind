"""Unit tests for OpenAI embedding wiring + Chroma LDU ingest (offline fakes)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.chunking.models import DocumentChunk
from src.retrieval.embeddings import OpenAIEmbeddingClient
from src.retrieval.ingest import ingest_chunks, semantic_search
from src.retrieval.vector_store import ChromaLDUStore


class _FakeEmbedder:
    """Deterministic bag-of-words-ish vectors (no network)."""

    model = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            # 8-dim fingerprint from character ordinals -- stable & cheap.
            base = [0.0] * 8
            for i, ch in enumerate(text.lower()[:64]):
                base[i % 8] += (ord(ch) % 31) / 31.0
            # L2-normalize-ish
            norm = sum(v * v for v in base) ** 0.5 or 1.0
            vectors.append([v / norm for v in base])
        return vectors


def _chunk(text: str, pages: list[int], hierarchy: list[str]) -> DocumentChunk:
    return DocumentChunk.create(
        text, parent_hierarchy=hierarchy, page_numbers=pages, chunk_type="prose"
    )


def test_openai_client_requires_api_key(monkeypatch):
    from src.config import VisionConfig

    monkeypatch.setattr(VisionConfig, "OPENAI_API_KEY", None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingClient(api_key=None)


def test_ingest_and_search_roundtrip(tmp_path: Path):
    store = ChromaLDUStore(persist_dir=tmp_path / "chroma", collection_name="test_ldus")
    embedder = _FakeEmbedder()
    chunks = [
        _chunk(
            "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
            [4],
            ["Executive summary"],
        ),
        _chunk(
            "Board governance and compliance notes for the year.",
            [10],
            ["Governance"],
        ),
        _chunk(
            "Warehouse logistics throughput rose twelve percent.",
            [3],
            ["Operations", "Logistics"],
        ),
    ]

    result = ingest_chunks(
        chunks,
        doc_id="docA",
        document_name="sample.pdf",
        store=store,
        embedder=embedder,
    )
    assert result.chunks_ingested == 3
    assert store.count == 3

    # Re-ingest same doc_id must replace, not duplicate.
    result2 = ingest_chunks(
        chunks[:2],
        doc_id="docA",
        document_name="sample.pdf",
        store=store,
        embedder=embedder,
    )
    assert result2.chunks_ingested == 2
    assert store.count == 2

    hits = semantic_search(
        "import tax expenditures ETB",
        doc_id="docA",
        top_k=2,
        store=store,
        embedder=embedder,
    )
    assert hits
    assert "tax" in hits[0].text.lower() or "ETB" in hits[0].text
    assert hits[0].doc_id == "docA"
    assert hits[0].document_name == "sample.pdf"
    assert hits[0].content_hash
    assert hits[0].page_numbers == [4]


def test_search_scoped_by_doc_id(tmp_path: Path):
    store = ChromaLDUStore(persist_dir=tmp_path / "chroma2", collection_name="scoped")
    embedder = _FakeEmbedder()
    ingest_chunks(
        [_chunk("Alpha revenue grew in Q3.", [1], ["Financials"])],
        doc_id="alpha",
        document_name="a.pdf",
        store=store,
        embedder=embedder,
    )
    ingest_chunks(
        [_chunk("Beta logistics network expanded.", [2], ["Ops"])],
        doc_id="beta",
        document_name="b.pdf",
        store=store,
        embedder=embedder,
    )
    hits = semantic_search(
        "logistics network",
        doc_id="beta",
        top_k=3,
        store=store,
        embedder=embedder,
    )
    assert all(h.doc_id == "beta" for h in hits)
