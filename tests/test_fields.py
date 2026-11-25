"""Schema field extraction (M8): values, schemas, page choice, grounding, rules (offline)."""

from __future__ import annotations

import json

import pytest

from src.document.model import BBox, Block, BlockType, DocumentModel, Page, PageQuality, Table, TableCell
from src.llm.base import LLMClient, LLMResult
from src.schemas import values as V
from src.schemas.extract import choose_pages, extract_fields, page_kinds
from src.schemas.schema import Schema, all_schemas, get_schema


# --- values ------------------------------------------------------------------------------


def test_amounts_keep_sign_and_scale():
    assert V.parse_amount("(4,790,941)") == -4790941
    assert V.parse_amount("ETB 1,234.50") == 1234.5
    assert V.parse_amount("-12") == -12
    assert V.scale_of("Birr'000") == 1e3 and V.scale_of("Birr'o0o") == 1e3
    assert V.scale_of("in millions of Birr") == 1e6 and V.scale_of("(in Mn. Birr)") == 1e6
    assert V.scale_of("ETB") == 1.0 and V.scale_of(None) == 1.0


def test_dates_in_the_ways_they_are_printed():
    from datetime import date

    d = date(2023, 6, 30)
    for s in ("30 June 2023", "June 30, 2023", "2023-06-30", "30/06/2023", "30-06-2023", "30 Jun 2023"):
        assert V.parse_date(s) == d, s
    assert V.parse_date("not a date") is None


def test_currency_codes_and_names():
    assert V.currency_code("Birr") == "ETB" and V.currency_code("Ethiopian Birr") == "ETB"
    assert V.currency_code("US$") == "USD" and V.currency_code("Birr'000") == "ETB"
    assert V.same_text("EthSwitch S.C.", "ETHSWITCH SHARE COMPANY")
    assert not V.same_text("Ethio Telecom", "Commercial Bank of Ethiopia")


# --- schemas -------------------------------------------------------------------------------


def test_both_schemas_load_with_their_rules():
    schemas = all_schemas()
    assert {"invoice", "financial_statement_summary"} <= set(schemas)
    inv = schemas["invoice"]
    assert inv.fields["line_items"].type == "list" and set(inv.fields["line_items"].item) == {"description", "quantity", "unit_price", "amount"}
    assert [r.kind for r in inv.rules] == ["sum", "sum_of_items", "product_of_item", "date_order"]
    fs = schemas["financial_statement_summary"]
    assert fs.fields["total_assets"].printed_on == "balance_sheet"


def test_a_rule_naming_an_unknown_field_is_rejected():
    with pytest.raises(ValueError):
        Schema.model_validate(
            {"name": "x", "fields": {"a": {"type": "money"}}, "rules": [{"name": "r", "kind": "sum", "total": "a", "parts": ["b"]}]}
        )


# --- a document to read ---------------------------------------------------------------------


def _page(number: int, title: str, rows: list[list[str]], *, extra: str = "") -> Page:
    blocks = [Block(block_id=f"p{number}-b0", type=BlockType.HEADING, text=title, bbox=BBox(x0=50, top=40, x1=400, bottom=60))]
    if extra:
        blocks.append(Block(block_id=f"p{number}-b1", type=BlockType.TEXT, text=extra, bbox=BBox(x0=50, top=600, x1=500, bottom=620)))
    blocks.append(Block(block_id=f"p{number}-b2", type=BlockType.TABLE, text=f"p{number}-t0"))
    cells = [
        TableCell(row=r, col=c, text=t, bbox=BBox(x0=50 + 120 * c, top=100 + 14 * r, x1=160 + 120 * c, bottom=112 + 14 * r))
        for r, row in enumerate(rows)
        for c, t in enumerate(row)
    ]
    table = Table(table_id=f"p{number}-t0", n_rows=len(rows), n_cols=max(len(r) for r in rows), cells=cells)
    return Page(number=number, width=595, height=842, blocks=blocks, tables=[table], quality=PageQuality(engine="text_layer", confidence=0.95))


def _report() -> DocumentModel:
    pages = [
        _page(1, "Annual Report 2023: Abay Bank S.C.", [["Contents", "Page"], ["Statement of financial position", "4"], ["Statement of profit or loss", "5"]]),
        _page(2, "Notes to the financial statements", [["Note", "2023"], ["Profit before tax used for tax", "1,200"]], extra="Tax computation"),
        _page(3, "Highlights", [["Item", "2023"], ["Total assets", "10,100"]]),
        _page(4, "Statement of financial position as at 30 June 2023 (Birr'000)", [
            ["", "2023", "2022"], ["Total assets", "10,000", "9,000"], ["Total liabilities", "7,000", "6,500"], ["Total equity", "3,000", "2,500"]]),
        _page(5, "Statement of profit or loss for the year ended 30 June 2023 (Birr'000)", [
            ["", "2023", "2022"], ["Profit / (Loss) before tax", "1,000", "800"], ["Income tax", "(250)", "(200)"], ["Profit for the year", "750", "600"]]),
        _page(6, "Statement of cash flows", [["", "2023"], ["Cash", "5"]]),
        _page(7, "Other information", [["", "2023"], ["Branches", "120"]]),
    ]
    return DocumentModel(doc_id="d1", file_name="r.pdf", sha256="x", page_count=len(pages), pages=pages)


class _PageReader(LLMClient):
    """Answers each page's call from a script keyed by the page number in the prompt."""

    provider = "fake"

    def __init__(self, answers: dict[int, dict]):
        super().__init__(model="fake-fields")
        self.answers = answers
        self.pages: list[int] = []

    def _chat(self, messages, **params):
        import re

        n = int(re.search(r"\npage (\d+):\n", messages[-1]["content"]).group(1))
        self.pages.append(n)
        return LLMResult(text=json.dumps(self.answers.get(n, {"fields": {}})), model=self.model, provider=self.provider)


def test_pages_are_chosen_by_statement_not_by_mentions():
    model, schema = _report(), get_schema("financial_statement_summary")
    kinds = {p.number: page_kinds(p, schema) for p in model.pages}
    assert kinds[4]["balance_sheet"] >= 4 and kinds[5]["income_statement"] >= 4  # "Profit / (Loss) before tax" counts
    assert kinds[1]["balance_sheet"] < 2  # a contents page lists titles but no figures
    assert choose_pages(model, schema, max_pages=3) == [1, 4, 5]  # the notes page that mentions a profit is not chosen


def test_fields_are_grounded_scaled_merged_and_checked():
    model, schema = _report(), get_schema("financial_statement_summary")
    llm = _PageReader({
        1: {"fields": {"entity_name": {"value": "Abay Bank S.C.", "ref": "p1-b0", "confidence": 0.95}}},
        3: {"fields": {"total_assets": {"value": "10,100", "ref": "p3-t0-r1-c1", "confidence": 0.9}}},
        4: {"fields": {
            "period_end": {"value": "30 June 2023", "ref": "p4-b0", "confidence": 0.95},
            "currency": {"value": "Birr", "ref": "p4-b0", "confidence": 0.9},
            "total_assets": {"value": "10,000", "unit": "Birr'000", "ref": "p4-t0-r2-c1", "confidence": 0.95},  # wrong row id
            "total_liabilities": {"value": "7,000", "unit": "Birr'000", "ref": "[p4-t0-r2-c1]", "confidence": 0.95},
            "total_equity": {"value": "3,000", "unit": "Birr'000", "ref": "p4-t0-r3-c1", "confidence": 0.95},
            # a profit figure read off the balance sheet: the income statement wins
            "profit_before_tax": {"value": "3,000", "ref": "p4-t0-r3-c1", "confidence": 0.9},
        }},
        5: {"fields": {
            "profit_before_tax": {"value": "1,000", "unit": "Birr'000", "ref": "p5-t0-r1-c1", "confidence": 0.9},
            "profit_after_tax": {"value": "4,321", "unit": "Birr'000", "ref": "p5-t0-r3-c1", "confidence": 0.95},  # not printed
        }},
    })
    res = extract_fields(model, schema, llm)
    f = res.fields
    assert f["total_assets"].value == 10_000_000 and f["total_assets"].page == 4
    assert f["total_assets"].ref == "p4-t0-r1-c1" and f["total_assets"].bbox  # re-pointed to the cell that prints it
    assert f["total_assets"].alternatives[0]["page"] == 3  # the highlights page disagreed
    assert f["total_liabilities"].value == 7_000_000 and f["total_liabilities"].ref == "p4-t0-r2-c1"
    assert f["profit_before_tax"].value == 1_000_000 and f["profit_before_tax"].page == 5
    assert f["period_end"].value == "2023-06-30" and f["currency"].value == "ETB"
    assert f["profit_after_tax"].status == "needs_review" and not f["profit_after_tax"].grounded
    assert {r["name"]: r["passed"] for r in res.rules}["balance_sheet_adds_up"] is True
    assert f["total_equity"].status == "auto"


def test_a_broken_rule_sends_its_fields_to_review():
    model, schema = _report(), get_schema("financial_statement_summary")
    llm = _PageReader({4: {"fields": {
        "total_assets": {"value": "10,000", "ref": "p4-t0-r1-c1", "confidence": 0.95},
        "total_liabilities": {"value": "7,000", "ref": "p4-t0-r2-c1", "confidence": 0.95},
        "total_equity": {"value": "2,500", "ref": "p4-t0-r3-c2", "confidence": 0.95},  # last year's column
    }}})
    res = extract_fields(model, schema, llm)
    assert not {r["name"]: r["passed"] for r in res.rules}["balance_sheet_adds_up"]
    assert {"total_assets", "total_liabilities", "total_equity"} <= set(res.needs_review)
    assert any("balance_sheet_adds_up" in r for r in res.fields["total_equity"].reasons)


def test_invoice_lines_and_their_rules():
    schema = get_schema("invoice")
    page = _page(1, "TAX INVOICE  Invoice No: INV-1  Date: 05/03/2026", [
        ["Description", "Qty", "Unit Price", "Amount"],
        ["Cement (bag)", "10", "1,180.00", "11,800.00"],
        ["Delivery", "1", "1,500.00", "1,500.00"],
        ["Subtotal", "", "", "13,300.00"], ["VAT 15%", "", "", "1,995.00"], ["Total", "", "", "15,295.00"],
    ])
    model = DocumentModel(doc_id="i1", file_name="i.pdf", sha256="y", page_count=1, pages=[page])
    llm = _PageReader({1: {
        "fields": {
            "invoice_number": {"value": "INV-1", "ref": "p1-b0", "confidence": 0.95},
            "invoice_date": {"value": "05/03/2026", "ref": "p1-b0", "confidence": 0.95},
            "subtotal": {"value": "13,300.00", "ref": "p1-t0-r3-c3", "confidence": 0.95},
            "vat_amount": {"value": "1,995.00", "ref": "p1-t0-r4-c3", "confidence": 0.95},
            "total_amount": {"value": "15,295.00", "ref": "p1-t0-r5-c3", "confidence": 0.95},
        },
        "items": [
            {"description": "Cement (bag)", "quantity": "10", "unit_price": "1,180.00", "amount": "11,800.00", "ref": "p1-t0-r1-c0"},
            {"description": "Delivery", "quantity": "1", "unit_price": "1,500.00", "amount": "1,500.00", "ref": "p1-t0-r2-c0"},
        ],
    }})
    res = extract_fields(model, schema, llm)
    assert res.fields["invoice_date"].value == "2026-03-05"  # day first, as Ethiopian invoices print it
    lines = res.fields["line_items"].value
    assert [x["amount"] for x in lines] == [11800.0, 1500.0] and lines[0]["bbox"]
    rules = {r["name"]: r["passed"] for r in res.rules}
    assert rules["total_is_subtotal_plus_vat"] and rules["lines_add_up_to_subtotal"] and rules["line_amount_is_quantity_times_price"]
    assert res.fields["seller_name"].status == "needs_review"  # required and not found
    assert res.fields["due_date"].status == "missing"  # optional and not printed


def test_a_business_line_cell_moves_to_its_total_column():
    from src.schemas.extract import total_column

    page = _page(9, "Statement of financial position", [
        ["", "General 2023", "Long-term 2023", "Total 2023", "Total 2022"],
        ["Total assets", "3,688,372,144", "345,822,566", "4,034,194,710", "3,069,252,734"],
    ])
    assert total_column(page, "p9-t0-r1-c1") == ("p9-t0-r1-c3", "4,034,194,710")
    assert total_column(page, "p9-t0-r1-c3") is None  # already the total


def test_names_prefer_the_full_form_over_an_acronym():
    from src.schemas.extract import _is_acronym

    assert _is_acronym("CBE", "Commercial Bank of Ethiopia")
    assert _is_acronym("Ethio RE", "Ethiopian Reinsurance Share Company")
    assert not _is_acronym("Ethio Telecom", "Commercial Bank of Ethiopia")


def test_a_scanned_value_that_breaks_a_rule_is_read_again_from_the_image():
    model, schema = _report(), get_schema("financial_statement_summary")
    for p in model.pages:
        p.quality.engine = "ocr"
    llm = _PageReader({4: {"fields": {
        "total_assets": {"value": "10,000", "ref": "p4-t0-r1-c1", "confidence": 0.95},
        "total_liabilities": {"value": "7,000", "ref": "p4-t0-r2-c1", "confidence": 0.95},
        "total_equity": {"value": "2,500", "ref": "p4-t0-r3-c2", "confidence": 0.95},  # OCR row trouble
    }}})

    class _Vision(LLMClient):
        provider = "fake"

        def __init__(self):
            super().__init__(model="fake-vision")
            self.seen = []

        def _chat(self, messages, **params):
            self.seen.append(messages[-1]["content"][-1]["detail"])
            return LLMResult(text=json.dumps({"fields": {"total_equity": {"value": "3,000", "confidence": 0.9}}}), model=self.model, provider=self.provider)

    vision = _Vision()
    res = extract_fields(model, schema, llm, page_image=lambda n: b"png", vision_llm=vision)
    eq = res.fields["total_equity"]
    assert eq.value == 3_000_000 and eq.status == "auto" and any("page image" in r for r in eq.reasons)  # Birr'000
    assert {r["name"]: r["passed"] for r in res.rules}["balance_sheet_adds_up"]
    assert set(vision.seen) == {"high"} and 4 in res.usage["pages_reread_from_image"]  # page 5 too: its profits were missing
