"""Unit tests for the evaluation suite's number handling and scorers."""

from __future__ import annotations

import pytest

from evaluation.numbers import (
    find_numbers,
    match_number_in_text,
    parse_number,
    presence_on_page,
)
from evaluation.schema import GoldFigure, GoldQuestion, QuestionType
from evaluation.scoring import is_refusal, list_recall, page_coverage, score_answer, score_figure


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1,234", 1234.0),
        ("(1,234.50)", -1234.5),
        ("-0.031", -0.031),
        ("22,996.62", 22996.62),
        ("1845", 1845.0),
        ("12.5%", 12.5),
        ("n/a", None),
    ],
)
def test_parse_number(text, value):
    assert parse_number(text) == value


def test_find_numbers_reads_scale_sign_and_percent():
    nums = find_numbers("Revenue was ETB 120.7 billion, down (3.2%) from 1,845 in 2020.")
    assert nums[0].absolute == pytest.approx(120.7e9)
    assert nums[1].value == -3.2 and nums[1].is_percent
    assert nums[2].value == 1845


@pytest.mark.parametrize(
    ("page", "state"),
    [
        ("| Vehicles | 22,996.62 | 7,202.33 |", "intact"),
        ("| Vehicles | 22,996. 62 |", "split"),
        ("| Burglary | 1 82,044 |", "missing"),  # different number entirely
        ("Burglary 182,044", "intact"),
        ("nothing here", "missing"),
    ],
)
def test_presence_on_page(page, state):
    value = "182,044" if "urglary" in page else "22,996.62"
    assert presence_on_page(value, page) == state or (state == "missing" and "1 82,044" in page)


def test_presence_detects_digit_split():
    assert presence_on_page("182,044", "Burglary 1 82,044") == "split"


def test_match_accepts_scaled_and_raw_values():
    gold_abs = 22996.62e6
    assert match_number_in_text("about ETB 23.0 billion", gold_abs, 22996.62, rel_tol=0.005).matched
    assert match_number_in_text("ETB 22,996.62 million", gold_abs, 22996.62).exact_scale
    raw = match_number_in_text("22,996.62", gold_abs, 22996.62)
    assert raw.matched and not raw.exact_scale
    assert not match_number_in_text("ETB 120.7 billion", gold_abs, 22996.62).matched


def test_match_checks_sign():
    m = match_number_in_text("a loss of 4,849,652", -4849652.0, -4849652.0)
    assert m.matched and not m.sign_ok
    assert match_number_in_text("(4,849,652)", -4849652.0, -4849652.0).sign_ok


def _figure(**kw):
    base = dict(
        figure_id="f1",
        doc_key="tax",
        page=19,
        row_label="Vehicles",
        column_label="2020/21",
        value_text="22,996.62",
        value=22996.62,
        scale=1e6,
    )
    base.update(kw)
    return GoldFigure(**base)


def test_score_figure_intact_row_and_fact():
    pages = {19: "| Vehicles | 9,002.46 | 7,202.33 | 22,996.62 |"}
    facts = [{"page_number": 19, "value_text": "22,996.62", "value": 22996.62}]
    r = score_figure(_figure(), pages, facts)
    assert r.on_gold_page == "intact" and r.row_intact and r.fact_correct


def test_score_figure_wrong_fact_value_and_wrong_page():
    pages = {18: "Vehicles 22,996.62", 19: "other text"}
    facts = [{"page_number": 19, "value_text": "22,996. 62", "value": 22996.0}]
    r = score_figure(_figure(), pages, facts)
    assert r.on_gold_page == "missing"
    assert r.on_any_page == "intact" and r.found_on_page == 18
    assert not r.fact_correct


def test_page_coverage_counts_silent_gaps():
    cov = page_coverage({1: "x" * 50, 2: "", 3: "y" * 30}, n_pages=5, failed_pages={4})
    assert cov["with_content"] == 2 and cov["flagged_failed"] == 1 and cov["silently_missing"] == 2


def _q(**kw):
    base = dict(
        question_id="q1",
        doc_key="tax",
        question="What were tax expenditures on vehicles in 2020/21?",
        qtype=QuestionType.LOOKUP_NUMBER,
        gold_value=22996.62e6,
        gold_value_raw=22996.62,
        gold_pages=[19],
    )
    base.update(kw)
    return GoldQuestion(**base)


def test_score_answer_lookup_and_citations():
    r = score_answer(_q(), "It was ETB 22,996.62 million [Page 19].", cited_pages=[19, 4])
    assert r.correct and r.citation_precision == 0.5 and r.citation_hit


def test_score_answer_wrong_number_and_false_refusal():
    assert not score_answer(_q(), "ETB 120.7 billion", cited_pages=[4]).correct
    r = score_answer(_q(), "Unverifiable / Source Not Found", cited_pages=[])
    assert not r.correct and r.refused and r.detail == "false refusal"


def test_score_unanswerable_and_list():
    unans = _q(qtype=QuestionType.UNANSWERABLE, gold_value=None, gold_pages=[])
    assert score_answer(unans, "The document does not contain this.", cited_pages=[]).correct
    assert not score_answer(unans, "It was 42.", cited_pages=[3]).correct
    lst = _q(qtype=QuestionType.LIST, gold_value=None, gold_items=["Animal products", "Vehicles", "Aircraft"])
    assert list_recall("animal products, vehicles and aircraft", lst.gold_items) == 1.0
    assert not score_answer(lst, "Vehicles only.", cited_pages=[19]).correct


def test_is_refusal():
    assert is_refusal("Unverifiable / Source Not Found - the document does not contain this information.")
    assert not is_refusal("Total revenue was ETB 5 billion.")


def test_text_layer_number_fragments_are_merged():
    from evaluation.draft.text_layer_figures import _merge_number_fragments

    words = [
        {"text": "Legal", "x0": 100, "x1": 120, "top": 10, "bottom": 18},
        {"text": "3", "x0": 324, "x1": 329, "top": 10, "bottom": 18},
        {"text": "9,480,469", "x0": 329.2, "x1": 370, "top": 10, "bottom": 18},
        {"text": "33,435,430", "x0": 407, "x1": 450, "top": 10, "bottom": 18},
    ]
    merged = [w["text"] for w in _merge_number_fragments(words)]
    assert merged == ["Legal", "39,480,469", "33,435,430"]


def test_review_sheet_round_trip(tmp_path, monkeypatch):
    import csv

    from evaluation import review, schema
    from evaluation.schema import GoldDocument, GoldenSet, ReviewStatus

    monkeypatch.setattr(schema, "GOLDEN_ROOT", tmp_path)
    golden = GoldenSet(
        version="t",
        documents=[GoldDocument(doc_key="tax", file_name="tax.pdf", sha256="x", pages=20,
                                doc_class="D_table_heavy", title="the tax report")],
        figures=[_figure(doc_key="tax")],
        questions=[_q()],
    )
    schema.save_golden(golden)
    sheet = review.export_sheet("t")
    rows = list(csv.DictReader(open(sheet, encoding="utf-8-sig")))
    for r in rows:
        r["status"] = "corrected" if r["kind"] == "figure" else "confirmed"
        r["corrected_value"] = "23,000.00" if r["kind"] == "figure" else ""
    with open(sheet, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=review.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    review.import_sheet(sheet, "t")
    after = schema.load_golden("t")
    assert after.figures[0].review is ReviewStatus.CORRECTED and after.figures[0].value == 23000.0
    assert after.questions[0].review is ReviewStatus.CONFIRMED
