"""Typed facts: number parsing, facts from tables and text, and the query spec (offline)."""

from __future__ import annotations

import pytest

from src.chunking.models import DocumentChunk
from src.document.model import BBox, Block, BlockType, DocumentModel, Page, PageQuality, Table, TableCell
from src.facts.extractor import extract_and_store, extract_facts_from_prose, extract_facts_from_table
from src.facts.numbers import find_numbers, parse_cell, scale_and_currency
from src.facts.query import FactQuery
from src.facts.typed import facts_from_model, normalize_period
from src.stores.memory import MemoryFactStore

# --- numbers -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text,value,percent",
    [
        ("(1,234.5)", -1234.5, False),
        ("1845", 1845.0, False),  # V1 read this as 184
        ("12345.67", 12345.67, False),  # V1 read this as 123
        ("−5.2", -5.2, False),
        ("12.5%", 12.5, True),
        ("(12.0)%", -12.0, True),
        ("3,261*", 3261.0, False),
        ("ETB 1,845", 1845.0, False),
    ],
)
def test_parse_cell_reads_whole_numbers_with_sign(text, value, percent):
    n = parse_cell(text)
    assert n is not None and n.value == pytest.approx(value) and n.percent is percent


@pytest.mark.parametrize("text", ["—", "N/A", "2023/24", "1.592.27", "(1,234"])
def test_parse_cell_rejects_what_is_not_one_number(text):
    assert parse_cell(text) is None


def test_find_numbers_keeps_scale_words_and_skips_period_digits():
    found = find_numbers("Import tax expenditures were ETB 120.7 billion in FY 2020/21, up 3.2% from (4.5).")
    assert [(n.value, n.scale, n.currency, n.percent) for n in found] == [
        (120.7, 1e9, "ETB", False), (3.2, 1.0, "", True), (-4.5, 1.0, "", False)]


@pytest.mark.parametrize(
    "text,scale,currency",
    [
        ("Table 4.2 Tax expenditures (in ETB million)", 1e6, "ETB"),
        ("Birr '000", 1e3, "ETB"),
        ("30 June 2021 Birr'o0o", 1e3, "ETB"),  # OCR of Birr'000
        ("(In Bn. of Birr)", 1e9, "ETB"),
        ("Amount in Million Birr", 1e6, "ETB"),
        ("እስከ 3ኛው ሩብ ዓመት የወጣ /በሺ ብር/", 1e3, "ETB"),  # Amharic: in thousand birr
        ("Revenue (Birr)", 1.0, "ETB"),
    ],
)
def test_scale_and_currency_from_captions(text, scale, currency):
    assert scale_and_currency(text) == (scale, currency)


def test_normalize_period():
    assert normalize_period("FY 2020/21") == normalize_period("2020-2021") == "2020/21"
    assert normalize_period("March EFY2017") == "march 2017"
    assert normalize_period("30 June 2024") == "june 2024"
    assert normalize_period("Total") == ""


# --- facts from the structured model -------------------------------------------


def _cell(r, c, text, header=False):
    return TableCell(row=r, col=c, text=text, is_header=header,
                     bbox=BBox(x0=100 + 80 * c, top=200 + 20 * r, x1=170 + 80 * c, bottom=215 + 20 * r))


def _model() -> DocumentModel:
    rows = [
        ["", "2022/23", "2023/24", "Share (%)"],
        ["Operating income", "", "", ""],
        ["Interest income", "1,200", "1,500", "60.0"],
        ["Fee income", "(300)", "450", "18.0"],
        ["Total", "900", "1,950", "78.0"],
    ]
    cells = [_cell(r, c, t, header=(r == 0)) for r, row in enumerate(rows) for c, t in enumerate(row)]
    table = Table(table_id="p3-t0", n_rows=5, n_cols=4, cells=cells, bbox=BBox(x0=90, top=190, x1=420, bottom=300))
    page = Page(
        number=3, width=600, height=800, tables=[table],
        blocks=[
            Block(block_id="p3-b0", type=BlockType.TEXT, text="Table 2: Income (in ETB million)"),
            Block(block_id="p3-b1", type=BlockType.TABLE, text="p3-t0"),
            Block(block_id="p3-b2", type=BlockType.TEXT, text="Staff strength reached 10,753 in 2023/24, and requests are answered within 5 business days."),
        ],
        quality=PageQuality(engine="docling", confidence=0.9),
    )
    return DocumentModel(doc_id="d", file_name="r.pdf", sha256="s", page_count=3,
                         pages=[Page(number=1, width=600, height=800, quality=PageQuality(engine="text_layer", confidence=0.9)),
                                Page(number=2, width=600, height=800, quality=PageQuality(engine="text_layer", confidence=0.9)), page])


def test_table_cells_become_typed_facts():
    facts = [f for f in facts_from_model(_model(), doc_id="d") if f.source == "table"]
    fee = next(f for f in facts if f.row_label == "Fee income" and f.column_label == "2022/23")
    assert fee.value == -300 and fee.scale == 1e6 and fee.unit == "ETB" and fee.page_number == 3
    assert fee.row_group == "Operating income" and fee.period_key == "2022/23"
    assert fee.bbox == [180.0, 260.0, 250.0, 275.0] and fee.table_id == "p3-t0"
    share = next(f for f in facts if f.row_label == "Interest income" and f.column_label == "Share (%)")
    assert share.unit == "%" and share.scale == 1.0


def test_text_numbers_become_facts_with_their_label():
    facts = [f for f in facts_from_model(_model(), doc_id="d") if f.source == "text"]
    staff = next(f for f in facts if f.value == 10753)
    assert "staff strength" in staff.row_label.lower() and staff.period == "2023/24"
    assert any(f.value == 5 and "within" in f.source_excerpt for f in facts)  # "5 business days"


def test_merged_label_and_number_cells_are_split():
    cells = [_cell(0, 0, "", True), _cell(0, 1, "Total 2019", True),
             _cell(1, 0, "Provision for Unearned Premium 260,239,974"), _cell(1, 1, "273,068,633")]
    table = Table(table_id="p1-t0", n_rows=2, n_cols=2, cells=cells)
    page = Page(number=1, width=600, height=800, tables=[table], quality=PageQuality(engine="docling", confidence=0.9))
    facts = facts_from_model(DocumentModel(doc_id="d", file_name="x", sha256="s", page_count=1, pages=[page]), doc_id="d")
    assert {f.value for f in facts if f.row_label == "Provision for Unearned Premium"} == {260239974, 273068633}


def test_chunk_facts_keep_the_old_entry_points():
    chunk = DocumentChunk.create(
        "Import tax expenditures were ETB 120.7 billion in FY 2020/21.", parent_hierarchy=["Summary"], page_numbers=[4]
    )
    top = extract_facts_from_prose(chunk, doc_id="d1", document_name="sample.pdf")[0]
    assert top.value == pytest.approx(120.7) and top.scale == 1e9 and top.unit == "ETB" and top.page_number == 4
    md = "| Category | FY 2020/21 |\n| --- | --- |\n| VAT expenditures | 44.6 |\n"
    table = DocumentChunk.create(md, parent_hierarchy=["Tax expenditure"], page_numbers=[16], chunk_type="table")
    vat = extract_facts_from_table(table, doc_id="d1")[0]
    assert vat.row_label == "VAT expenditures" and vat.period_key == "2020/21" and vat.page_number == 16


def test_store_replace_and_search():
    store = MemoryFactStore()
    chunk = DocumentChunk.create("Revenue was ETB 10.5 billion in FY 2019/20.", parent_hierarchy=["Financials"], page_numbers=[2])
    result = extract_and_store([chunk], doc_id="docA", document_name="a.pdf", store=store)
    assert result.facts_written >= 1 and store.count("docA") == result.facts_written
    assert store.search(doc_id="docA", metric_contains="Revenue")
    again = extract_and_store([chunk], doc_id="docA", document_name="a.pdf", store=store)
    assert store.count("docA") == again.facts_written


# --- the query spec ----------------------------------------------------------------


def _store() -> MemoryFactStore:
    store = MemoryFactStore()
    store.replace_doc_facts("d", facts_from_model(_model(), doc_id="d", document_name="r.pdf"))
    return store


def test_spec_rejects_bad_input_and_needs_two_periods_for_a_change():
    with pytest.raises(ValueError):
        FactQuery(op="lookup", metric="  123  ")
    with pytest.raises(ValueError):
        FactQuery.model_validate({"op": "drop table", "metric": "x"})
    assert FactQuery(op="percent_change", metric="fee income", periods=["2023/24"]).op == "lookup"
    assert FactQuery(op="lookup", metric="x", limit=5).limit == 5
    with pytest.raises(ValueError):
        FactQuery(op="lookup", metric="x", limit=10_000)


def test_lookup_and_percent_change_are_computed_from_cells():
    store = _store()
    looked = store.run_query(FactQuery(op="lookup", metric="fee income", periods=["2023/24"]), doc_id="d")
    assert looked.facts[0].value == 450
    change = store.run_query(FactQuery(op="percent_change", metric="fee income", periods=["2022/23", "2023/24"]), doc_id="d")
    assert change.computed[0].value == pytest.approx(250.0)  # (450 - (-300)) / 300 x 100
    assert change.computed[0].unit == "%" and len(change.computed[0].inputs) == 2


def test_sum_runs_over_the_column_without_total_rows():
    result = _store().run_query(FactQuery(op="sum", metric="interest income", periods=["2023/24"]), doc_id="d")
    assert result.computed[0].value == pytest.approx((1500 + 450) * 1e6)
