"""Offline tests for indexing a document model into stores, and the query CLI."""

from __future__ import annotations

import pytest

from src.document.model import Block, BlockType, DocumentModel, Page, PageQuality
from src.pipeline.ingest import index_document
from src.retrieval.ingest import semantic_search
from src.stores.memory import memory_stores


class _FakeEmbedder:
    model = "fake"

    def __init__(self):
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        out = []
        for text in texts:
            base = [0.0] * 8
            for i, ch in enumerate(text.lower()[:64]):
                base[i % 8] += (ord(ch) % 31) / 31.0
            norm = sum(v * v for v in base) ** 0.5 or 1.0
            out.append([v / norm for v in base])
        return out


def _model() -> DocumentModel:
    def page(n, *blocks):
        return Page(
            number=n,
            width=600,
            height=800,
            blocks=[Block(block_id=f"p{n}-b{i}", type=t, text=x) for i, (t, x) in enumerate(blocks)],
            quality=PageQuality(engine="text_layer", confidence=0.9),
        )

    return DocumentModel(
        doc_id="ignored",
        file_name="sample.pdf",
        sha256="s",
        page_count=2,
        pages=[
            page(1, (BlockType.HEADING, "Executive summary"),
                 (BlockType.TEXT, "Import tax expenditures were ETB 120.7 billion in FY 2020/21.")),
            page(2, (BlockType.HEADING, "Governance"), (BlockType.TEXT, "Board governance notes.")),
        ],
    )


def test_index_document_writes_chunks_facts_and_pageindex():
    stores = memory_stores()
    embedder = _FakeEmbedder()
    result, chunks = index_document(
        _model(), doc_id="doc1", document_name="sample.pdf", stores=stores, embedder=embedder
    )
    assert result.chunk_count == len(chunks) >= 1
    assert result.embedded is True
    assert stores.chunks.count("doc1") == result.chunk_count
    assert result.facts_written >= 1
    assert stores.facts.search(doc_id="doc1", metric_contains="import tax")
    assert stores.pageindex.load("doc1") is not None
    assert result.pageindex_sections >= 1
    assert set(result.seconds) == {"chunk", "index", "embed"}

    hits = semantic_search("import tax", doc_id="doc1", store=stores.chunks, embedder=embedder)
    assert hits and hits[0].document_name == "sample.pdf"
    assert any(4 > p >= 1 for h in hits for p in h.page_numbers)


def test_index_document_without_embeddings_is_free():
    stores = memory_stores()
    embedder = _FakeEmbedder()
    result, _ = index_document(
        _model(), doc_id="doc2", document_name="s.pdf", stores=stores, embedder=embedder, embed=False
    )
    assert result.embedded is False
    assert embedder.calls == 0
    assert stores.chunks.count("doc2") == result.chunk_count
    # Chunks without vectors are stored but never returned by vector search.
    assert stores.chunks.query([1.0] * 8, doc_id="doc2") == []


def test_reindex_replaces_instead_of_duplicating():
    stores = memory_stores()
    embedder = _FakeEmbedder()
    first, _ = index_document(_model(), doc_id="d", document_name="s.pdf", stores=stores, embedder=embedder)
    second, _ = index_document(_model(), doc_id="d", document_name="s.pdf", stores=stores, embedder=embedder)
    assert stores.chunks.count("d") == second.chunk_count == first.chunk_count
    assert stores.facts.count("d") == second.facts_written


def test_run_query_cli_help():
    from run_query import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_run_query_cli_requires_text():
    from run_query import main

    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
