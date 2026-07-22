"""Unit tests for FactTable extractor + SQLite store (Phase 4 Step 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.chunking.models import DocumentChunk
from src.facts.extractor import (
    extract_and_store,
    extract_facts_from_chunk,
    extract_facts_from_prose,
    extract_facts_from_table,
)
from src.facts.store import FactStore


def test_prose_extracts_etb_fact():
    chunk = DocumentChunk.create(
        "Import tax expenditures were ETB 120.7 billion in FY 2020/21, "
        "which represented around 2.8% of GDP.",
        parent_hierarchy=["Executive summary"],
        page_numbers=[4],
    )
    facts = extract_facts_from_prose(
        chunk, doc_id="d1", document_name="sample.pdf"
    )
    assert facts
    top = facts[0]
    assert "tax" in top.metric.lower() or "Import" in top.metric
    assert top.value == pytest.approx(120.7)
    assert "billion" in top.unit.lower()
    assert "2020" in top.period
    assert top.page_number == 4
    assert top.content_hash


def test_table_extracts_numeric_cells():
    md = """| Category | FY 2020/21 | Share |
| --- | --- | --- |
| VAT expenditures | ETB 44.6 billion | 37% |
| Customs duty | ETB 38.9 billion | 32% |
"""
    chunk = DocumentChunk.create(
        md,
        parent_hierarchy=["Tax expenditure estimates"],
        page_numbers=[16],
        chunk_type="table",
    )
    facts = extract_facts_from_table(
        chunk, doc_id="d1", document_name="sample.pdf"
    )
    assert len(facts) >= 2
    vat = next(f for f in facts if "VAT" in f.metric and f.value == pytest.approx(44.6))
    assert "2020" in vat.period or "2020" in vat.metric
    assert vat.page_number == 16


def test_store_replace_and_search(tmp_path: Path):
    store = FactStore(db_path=tmp_path / "facts.db")
    chunk = DocumentChunk.create(
        "Revenue was ETB 10.5 billion in FY 2019/20.",
        parent_hierarchy=["Financials"],
        page_numbers=[2],
    )
    result = extract_and_store(
        [chunk], doc_id="docA", document_name="a.pdf", store=store
    )
    assert result.facts_written >= 1
    assert store.count("docA") == result.facts_written

    hits = store.search(doc_id="docA", metric_contains="Revenue")
    assert hits
    assert hits[0].document_name == "a.pdf"

    # Idempotent replace
    result2 = extract_and_store(
        [chunk], doc_id="docA", document_name="a.pdf", store=store
    )
    assert store.count("docA") == result2.facts_written

    rows = store.select(
        "SELECT metric, value_text FROM facts WHERE doc_id = ?", ("docA",)
    )
    assert rows and "metric" in rows[0]


def test_select_rejects_non_select(tmp_path: Path):
    store = FactStore(db_path=tmp_path / "facts2.db")
    with pytest.raises(ValueError):
        store.select("DELETE FROM facts")


def test_extract_facts_from_chunk_combines_paths():
    chunk = DocumentChunk.create(
        "Customs duty expenditures were ETB 38.9 billion in FY 2020/21.",
        parent_hierarchy=["4.2 Customs duty"],
        page_numbers=[22],
        chunk_type="prose",
    )
    facts = extract_facts_from_chunk(chunk, doc_id="x", document_name="s.pdf")
    assert any(f.value == pytest.approx(38.9) for f in facts)
