"""Unit tests for the three Query Agent tools (Phase 4 Step 5)."""

from __future__ import annotations

from pathlib import Path

from src.chunking.models import DocumentChunk
from src.facts.extractor import extract_and_store
from src.facts.store import FactStore
from src.models.page_index import PageIndex, SectionNode
from src.models.query import ToolName
from src.pageindex.builder import build_page_index, save_page_index
from src.query.tools import pageindex_navigate, semantic_search, structured_query
from src.retrieval.ingest import ingest_chunks
from src.retrieval.vector_store import ChromaLDUStore


class _FakeEmbedder:
    model = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            base = [0.0] * 8
            for i, ch in enumerate(text.lower()[:64]):
                base[i % 8] += (ord(ch) % 31) / 31.0
            norm = sum(v * v for v in base) ** 0.5 or 1.0
            out.append([v / norm for v in base])
        return out


def _chunk(text: str, hierarchy: list[str], pages: list[int]) -> DocumentChunk:
    return DocumentChunk.create(
        text, parent_hierarchy=hierarchy, page_numbers=pages, chunk_type="prose"
    )


def test_pageindex_navigate_returns_sections(tmp_path: Path):
    chunks = [
        _chunk("Logistics throughput rose.", ["Ops", "Logistics"], [3]),
        _chunk("Board governance notes.", ["Governance"], [10]),
        _chunk(
            "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
            ["Executive summary"],
            [4],
        ),
    ]
    index = build_page_index(
        chunks, doc_id="t1", source_filename="sample.pdf",
        summarize=True, llm_client=None,
    )
    save_page_index(index, directory=tmp_path)

    result = pageindex_navigate(
        "logistics throughput", doc_id="t1", pageindex_dir=tmp_path
    )
    assert result.tool is ToolName.PAGEINDEX_NAVIGATE
    assert not result.is_empty
    assert result.hits[0].title == "Logistics"
    assert result.hits[0].page_number == 3
    assert result.trace.summary


def test_semantic_search_tool(tmp_path: Path):
    store = ChromaLDUStore(persist_dir=tmp_path / "chroma", collection_name="tools")
    embedder = _FakeEmbedder()
    chunks = [
        _chunk(
            "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
            ["Executive summary"],
            [4],
        ),
        _chunk("Governance and board notes.", ["Governance"], [10]),
    ]
    ingest_chunks(
        chunks, doc_id="docA", document_name="sample.pdf",
        store=store, embedder=embedder,
    )
    result = semantic_search(
        "import tax expenditures",
        doc_id="docA",
        top_k=2,
        store=store,
        embedder=embedder,
    )
    assert result.tool is ToolName.SEMANTIC_SEARCH
    assert result.hits
    assert result.hits[0].content_hash
    assert result.hits[0].page_number == 4


def test_structured_query_filters(tmp_path: Path):
    store = FactStore(db_path=tmp_path / "facts.db")
    chunk = DocumentChunk.create(
        "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
        parent_hierarchy=["Executive summary"],
        page_numbers=[4],
    )
    extract_and_store(
        [chunk], doc_id="docA", document_name="sample.pdf", store=store
    )
    result = structured_query(
        doc_id="docA",
        metric_contains="tax",
        period_contains="2020",
        store=store,
    )
    assert result.tool is ToolName.STRUCTURED_QUERY
    assert result.hits
    assert result.hits[0].extra.get("value") == 120.7
    assert "tax" in result.hits[0].title.lower() or "Import" in result.hits[0].title


def test_structured_query_select_sql(tmp_path: Path):
    store = FactStore(db_path=tmp_path / "facts2.db")
    chunk = DocumentChunk.create(
        "Revenue was ETB 10.5 billion in FY 2019/20.",
        parent_hierarchy=["Financials"],
        page_numbers=[2],
    )
    extract_and_store([chunk], doc_id="docB", document_name="b.pdf", store=store)
    result = structured_query(
        sql="SELECT * FROM facts WHERE doc_id = 'docB'",
        store=store,
    )
    assert result.hits
    assert result.hits[0].doc_id == "docB"


def test_empty_inputs_return_empty_evidence():
    assert pageindex_navigate("", doc_id="x", index=PageIndex(doc_id="x")).is_empty
    # semantic_search with empty query should not call embedder
    result = semantic_search("", embedder=_FakeEmbedder())
    assert result.is_empty
