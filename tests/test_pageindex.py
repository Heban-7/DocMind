"""Unit tests for PageIndex builder + navigate (Phase 4 Step 2)."""

from __future__ import annotations

from pathlib import Path

from src.chunking.models import DocumentChunk
from src.pageindex.builder import (
    build_page_index,
    load_page_index,
    save_page_index,
)
from src.pageindex.navigate import navigate, score_section


def _chunk(text: str, hierarchy: list[str], pages: list[int], ctype: str = "prose"):
    return DocumentChunk.create(
        text, parent_hierarchy=hierarchy, page_numbers=pages, chunk_type=ctype
    )


def _sample_chunks() -> list[DocumentChunk]:
    return [
        _chunk("Opening of the annual report body.", ["Annual Report"], [1]),
        _chunk(
            "Operations overview for the year. Logistics improved.",
            ["Annual Report", "Operations"],
            [2, 3],
        ),
        _chunk(
            "Warehouse throughput rose 12 percent this quarter.",
            ["Annual Report", "Operations", "Logistics"],
            [3],
            "table",
        ),
        _chunk(
            "Board governance and compliance notes.",
            ["Annual Report", "Governance"],
            [10],
        ),
        _chunk(
            "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
            ["Executive summary"],
            [4],
        ),
    ]


def test_build_tree_hierarchy_and_page_spans():
    index = build_page_index(
        _sample_chunks(),
        doc_id="demo",
        source_filename="demo.pdf",
        summarize=True,
        llm_client=None,  # force extractive summaries
    )
    assert index.doc_id == "demo"
    titles = {n.title for n in index.iter_nodes()}
    assert "Operations" in titles
    assert "Logistics" in titles
    assert "Governance" in titles

    ops = next(n for n in index.iter_nodes() if n.title == "Operations")
    # Ops own pages 2-3 plus Logistics child on 3 ? span includes 2..3
    assert ops.page_start == 2
    assert ops.page_end == 3
    assert any(c.title == "Logistics" for c in ops.children)

    logistics = next(n for n in index.iter_nodes() if n.title == "Logistics")
    assert "table" in logistics.data_types_present
    assert logistics.summary  # extractive fallback filled


def test_save_and_load_roundtrip(tmp_path: Path):
    index = build_page_index(
        _sample_chunks(), doc_id="roundtrip", summarize=False, llm_client=None
    )
    path = save_page_index(index, directory=tmp_path)
    loaded = load_page_index("roundtrip", directory=tmp_path)
    assert loaded.doc_id == "roundtrip"
    assert len(loaded.iter_nodes()) == len(index.iter_nodes())
    assert path.exists()


def test_navigate_returns_top_relevant_sections():
    index = build_page_index(
        _sample_chunks(), doc_id="nav", summarize=True, llm_client=None
    )
    hits = navigate(index, "logistics warehouse throughput", top_k=3)
    assert hits
    assert hits[0][0].title == "Logistics"
    assert hits[0][1] > 0

    tax_hits = navigate(index, "import tax expenditures FY 2020", top_k=2)
    assert tax_hits[0][0].title == "Executive summary"


def test_navigate_empty_topic():
    index = build_page_index(
        _sample_chunks(), doc_id="nav2", summarize=False, llm_client=None
    )
    assert navigate(index, "   ") == []


def test_score_section_title_beats_unrelated():
    index = build_page_index(
        _sample_chunks(), doc_id="score", summarize=False, llm_client=None
    )
    logistics = next(n for n in index.iter_nodes() if n.title == "Logistics")
    governance = next(n for n in index.iter_nodes() if n.title == "Governance")
    assert score_section("logistics", logistics) > score_section(
        "logistics", governance
    )
