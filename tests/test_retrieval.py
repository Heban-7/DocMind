"""Unit tests for embedding wiring + chunk ingest and search (offline fakes)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.chunking.models import DocumentChunk
from src.retrieval.embeddings import OpenAIEmbeddingClient
from src.retrieval.ingest import ingest_chunks, semantic_search
from src.stores.memory import MemoryChunkStore


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
    store = MemoryChunkStore()
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
    assert store.count() == 3

    # Re-ingest same doc_id must replace, not duplicate.
    result2 = ingest_chunks(
        chunks[:2],
        doc_id="docA",
        document_name="sample.pdf",
        store=store,
        embedder=embedder,
    )
    assert result2.chunks_ingested == 2
    assert store.count() == 2

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
    store = MemoryChunkStore()
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


# --- M6: hybrid search and reranking -----------------------------------------------


def test_keyword_query_ors_content_words_and_keeps_quoted_phrases():
    from src.retrieval.keywords import keyword_query

    q = keyword_query('According to the annual report, what is the figure for “Government Bond” for 2024?')
    assert q.startswith("(government <-> bond)") and "2024" in q and "what" not in q and "according" not in q
    assert keyword_query("what is the") == ""


def test_hybrid_search_finds_an_exact_label_that_vectors_rank_low():
    from src.retrieval.ingest import ingest_chunks, retrieve

    store = MemoryChunkStore()
    embedder = _FakeEmbedder()
    chunks = [
        _chunk("Overview of the bank's strategy and outlook for the coming year.", [1], ["Overview"]),
        _chunk("| Item | 2024 |\n| --- | --- |\n| Government Bond | 1,230,978 |", [73], ["Note 23 Investments"]),
        _chunk("Board governance and compliance notes for the year.", [10], ["Governance"]),
    ]
    ingest_chunks(chunks, doc_id="d", document_name="CBE Annual Report 2023-24.pdf", store=store, embedder=embedder)
    hits = retrieve('What is the figure for "Government Bond" for 2024?', store=store, doc_id="d", top_k=2, embedder=embedder, rerank=False)
    assert hits[0].page_numbers == [73]
    assert hits[0].context.startswith("CBE Annual Report 2023-24 > Note 23")


def test_reranker_order_wins_when_it_runs(monkeypatch):
    from src.retrieval import rerank
    from src.retrieval.ingest import ingest_chunks, retrieve

    store = MemoryChunkStore()
    embedder = _FakeEmbedder()
    chunks = [_chunk(f"Paragraph number {i} about revenue.", [i], ["S"]) for i in range(1, 5)]
    ingest_chunks(chunks, doc_id="d", store=store, embedder=embedder)
    monkeypatch.setattr(rerank, "scores", lambda q, passages: [0.1, 0.2, 0.9, 0.3][: len(passages)])
    hits = retrieve("revenue", store=store, doc_id="d", top_k=4, embedder=embedder)
    assert hits[0].relevance == 0.9 and hits[0].score == 0.9


def test_reranker_is_skipped_when_off_or_for_ethiopic(monkeypatch):
    from src.retrieval import rerank

    monkeypatch.setenv("DOCMIND_RERANKER", "off")
    assert rerank.scores("what was revenue?", ["a", "b"]) is None
    monkeypatch.setenv("DOCMIND_RERANKER", "some/model")
    assert rerank.scores("የበጀት ዓመቱ ገቢ ስንት ነበር?", ["a", "b"]) is None


def test_a_slow_query_embedding_falls_back_to_keywords(monkeypatch):
    """A hung embedding call must not use up the answer's time limit."""
    from src.llm import usage
    from src.llm.errors import LLMError

    store = MemoryChunkStore()
    ingest_chunks(
        [_chunk("Import tax expenditures were ETB 120.7 billion.", [4], ["Summary"])],
        doc_id="docA", document_name="sample.pdf", store=store, embedder=_FakeEmbedder(),
    )

    class _Hung:
        model = "fake"

        def embed(self, texts):
            # what post_json raises once the (inner) time limit has passed
            raise LLMError("no time left", kind="deadline", provider="openai")

    monkeypatch.setenv("DOCMIND_QUERY_EMBED_BUDGET_S", "2")
    with usage.deadline(60):
        hits = semantic_search("import tax expenditures", doc_id="docA", top_k=2, store=store, embedder=_Hung())
    assert hits and hits[0].page_numbers == [4]

    # with the answer's own limit used up, the error still stops the answer
    with usage.deadline(0.5), pytest.raises(LLMError):
        semantic_search("import tax expenditures", doc_id="docA", top_k=2, store=store, embedder=_Hung())
