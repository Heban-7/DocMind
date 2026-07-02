"""
Fast unit tests for the Triage Agent's PURE logic -- no PDFs required.

These pin down the heuristic math (origin/layout/cost decisions, column and
language detection, keyword domain scoring) and prove the Pydantic schema
rejects impossible data.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agents.domain import KeywordDomainClassifier
from src.agents.signals import (
    detect_language,
    estimate_column_count,
    math_symbol_ratio,
)
from src.agents.triage import (
    classify_layout,
    classify_origin,
    estimate_cost,
    resolve_sample_size,
    sample_page_indices,
)
from src.config import Thresholds
from src.models.document_profile import (
    DomainHint,
    ExtractionCost,
    LanguageGuess,
    LayoutComplexity,
    OriginType,
)


# --- Origin classification --------------------------------------------------
def test_origin_native_digital_when_pages_are_text():
    assert classify_origin(1.0, 0.0, 0.0) == OriginType.NATIVE_DIGITAL


def test_origin_scanned_when_pages_are_images():
    assert classify_origin(0.05, 0.95, 0.0) == OriginType.SCANNED_IMAGE


def test_origin_mixed_when_neither_dominates():
    assert classify_origin(0.5, 0.4, 0.0) == OriginType.MIXED


def test_origin_form_fillable_when_widgets_dominate():
    # Form detection wins even if there is text.
    assert classify_origin(0.9, 0.0, 0.6) == OriginType.FORM_FILLABLE


# --- Layout classification --------------------------------------------------
def test_layout_single_column_when_no_strong_signal():
    assert classify_layout(0.0, 0.0, 0.0) == LayoutComplexity.SINGLE_COLUMN


def test_layout_table_heavy():
    assert classify_layout(0.7, 0.0, 0.0) == LayoutComplexity.TABLE_HEAVY


def test_layout_figure_heavy():
    assert classify_layout(0.0, 0.8, 0.0) == LayoutComplexity.FIGURE_HEAVY


def test_layout_multi_column():
    assert classify_layout(0.0, 0.0, 0.7) == LayoutComplexity.MULTI_COLUMN


def test_layout_mixed_when_two_signals_fire():
    assert classify_layout(0.7, 0.0, 0.7) == LayoutComplexity.MIXED


# --- Cost estimation --------------------------------------------------------
def test_cost_vision_for_scanned():
    cost = estimate_cost(OriginType.SCANNED_IMAGE, LayoutComplexity.FIGURE_HEAVY)
    assert cost == ExtractionCost.NEEDS_VISION_MODEL


def test_cost_layout_for_complex_digital():
    cost = estimate_cost(OriginType.NATIVE_DIGITAL, LayoutComplexity.TABLE_HEAVY)
    assert cost == ExtractionCost.NEEDS_LAYOUT_MODEL


def test_cost_fast_text_for_simple_digital():
    cost = estimate_cost(OriginType.NATIVE_DIGITAL, LayoutComplexity.SINGLE_COLUMN)
    assert cost == ExtractionCost.FAST_TEXT_SUFFICIENT


# --- Column estimation ------------------------------------------------------
def _word(x0: float, x1: float) -> dict:
    return {"x0": x0, "x1": x1, "text": "w"}


def test_single_column_detection():
    words = [_word(250, 350) for _ in range(40)]  # all centered
    assert estimate_column_count(words, page_width=600) == 1


def test_two_column_detection():
    left = [_word(50, 150) for _ in range(20)]  # center ~0.17
    right = [_word(450, 550) for _ in range(20)]  # center ~0.83
    assert estimate_column_count(left + right, page_width=600) == 2


def test_too_little_text_defaults_to_single_column():
    assert estimate_column_count([_word(50, 150)], page_width=600) == 1


# --- Language detection -----------------------------------------------------
def test_detect_english():
    code, conf = detect_language("This is a clearly English sentence.")
    assert code == "en" and conf > 0.9


def test_detect_amharic_ethiopic_script():
    # Built from Ethiopic-block code points (U+1200-U+137F) so the test file
    # stays ASCII-safe regardless of the editor's encoding.
    amharic = "".join(chr(cp) for cp in range(0x1208, 0x1208 + 20))
    code, conf = detect_language(amharic)
    assert code == "am" and conf > 0.9


def test_detect_undetermined_when_empty():
    assert detect_language("") == ("und", 0.0)


# --- Keyword domain classifier ----------------------------------------------
def test_domain_financial():
    text = "The balance sheet shows revenue, assets, liabilities and net profit."
    domain, conf = KeywordDomainClassifier().classify(text)
    assert domain == DomainHint.FINANCIAL and conf > 0.0


def test_domain_legal():
    text = "Whereas the plaintiff and defendant agree, this contract clause is law."
    domain, _ = KeywordDomainClassifier().classify(text)
    assert domain == DomainHint.LEGAL


def test_domain_general_when_no_keywords():
    domain, conf = KeywordDomainClassifier().classify("the quick brown fox jumps")
    assert domain == DomainHint.GENERAL and conf == 0.0


# --- Page sampling ----------------------------------------------------------
def test_sampling_small_doc_returns_all_pages():
    assert sample_page_indices(5, 12) == [0, 1, 2, 3, 4]


def test_sampling_large_doc_is_bounded_and_in_range():
    indices = sample_page_indices(100, 12)
    assert len(indices) <= 12
    assert all(0 <= i < 100 for i in indices)
    assert indices == sorted(set(indices))  # unique + ordered


# --- Adaptive sample size ---------------------------------------------------
def test_adaptive_sample_floor_for_small_docs():
    # 20 pages * 5% = 1, so we clamp up to the floor.
    assert resolve_sample_size(20) == Thresholds.SAMPLE_MIN_PAGES


def test_adaptive_sample_ceiling_for_huge_docs():
    # 600 pages * 5% = 30, clamped down to the ceiling.
    assert resolve_sample_size(600) == Thresholds.SAMPLE_MAX_PAGES


def test_adaptive_sample_scales_in_between():
    # 360 pages * 5% = 18, between floor (12) and ceiling (24).
    assert resolve_sample_size(360) == 18


# --- Math symbol ratio ------------------------------------------------------
def test_math_ratio_zero_for_plain_prose():
    chars = [{"text": c} for c in "hello world"]
    assert math_symbol_ratio(chars) == 0.0


def test_math_ratio_counts_strong_symbols_only():
    # 2 strong math chars (U+2211 summation, U+221A sqrt) of 4 non-space chars.
    chars = [{"text": c} for c in "a\u2211b\u221a"]
    assert math_symbol_ratio(chars) == pytest.approx(0.5)


def test_math_ratio_ignores_financial_punctuation():
    # Hyphens, slashes, percent and pipes must NOT count as math.
    chars = [{"text": c} for c in "12/05-2024 50% |x|"]
    assert math_symbol_ratio(chars) == 0.0


# --- Pydantic guardrails ----------------------------------------------------
def test_confidence_out_of_range_is_rejected():
    with pytest.raises(ValidationError):
        LanguageGuess(code="en", confidence=1.5)


def test_unknown_enum_value_is_rejected():
    with pytest.raises(ValidationError):
        LanguageGuess(code="en", confidence="not-a-number")  # type: ignore[arg-type]
