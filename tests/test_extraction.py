"""
Unit tests for Phase 2: the LLM layer, budget guard, provider factory, the
Docling/MinerU layout selector, and the extraction router.

These avoid real network/model calls by injecting fakes and monkeypatching, so
they run fast and offline.
"""

from __future__ import annotations

import pytest

from src.config import DEFAULT_SAMPLE_PDF, VisionConfig
from src.extraction import _docling_support as ds
from src.extraction.fast_text import FastTextEngine
from src.extraction.layout_docling import DoclingLayoutEngine
from src.extraction.layout_mineru import MinerULayoutEngine
from src.extraction.layout_selector import LayoutStrategySelector
from src.extraction.router import ExtractionRouter
from src.extraction.vision_augmented import VisionAugmentedEngine
from src.llm.base import LLMResult, VisionLLMClient
from src.llm.budget import BudgetExceededError, BudgetGuard
from src.llm.factory import build_vision_client
from src.llm.pricing import estimate_cost
from src.models.document_profile import (
    DocumentProfile,
    DocumentSignals,
    DomainHint,
    ExtractionCost,
    LanguageGuess,
    LayoutComplexity,
    OriginType,
)


# --- Helpers ----------------------------------------------------------------
def _make_profile(
    tier: ExtractionCost, math_ratio: float = 0.0
) -> DocumentProfile:
    return DocumentProfile(
        doc_id="deadbeefcafe",
        source_filename="x.pdf",
        source_path="x.pdf",
        page_count=3,
        origin_type=OriginType.NATIVE_DIGITAL,
        layout_complexity=LayoutComplexity.SINGLE_COLUMN,
        language=LanguageGuess(code="en", confidence=1.0),
        domain_hint=DomainHint.GENERAL,
        domain_confidence=0.0,
        estimated_cost=tier,
        signals=DocumentSignals(
            page_count=3,
            pages_analyzed=3,
            text_page_ratio=1.0,
            scanned_page_ratio=0.0,
            sparse_page_ratio=0.0,
            avg_char_density=10.0,
            avg_image_area_ratio=0.0,
            max_image_area_ratio=0.0,
            table_page_ratio=0.0,
            avg_table_area_ratio=0.0,
            multi_column_page_ratio=0.0,
            form_field_page_ratio=0.0,
            avg_math_symbol_ratio=math_ratio,
        ),
        triage_version="test",
    )


class _FakeClient(VisionLLMClient):
    provider = "fake"

    def __init__(self, cost_per_call: float = 0.0):
        super().__init__("fake-model")
        self.cost_per_call = cost_per_call
        self.calls = 0

    def chat(
        self,
        messages,
        *,
        response_format=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text=f"# Page transcription {self.calls}",
            model=self.model,
            provider=self.provider,
            input_tokens=10,
            output_tokens=20,
            cost_usd=self.cost_per_call,
        )


# --- Pricing & budget -------------------------------------------------------
def test_pricing_uses_known_rate():
    cost = estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.15 + 0.60)


def test_pricing_unknown_model_falls_back():
    assert estimate_cost("totally-unknown", 1_000_000, 0) == pytest.approx(1.00)


def test_budget_guard_blocks_after_cap():
    guard = BudgetGuard(max_usd=0.10)
    guard.assert_can_spend()  # ok at start
    guard.record(0.10)
    with pytest.raises(BudgetExceededError):
        guard.assert_can_spend()


# --- Provider factory -------------------------------------------------------
def _clear_provider_env(monkeypatch):
    monkeypatch.setattr(VisionConfig, "PROVIDER", None)
    monkeypatch.setattr(VisionConfig, "MODEL", None)
    monkeypatch.setattr(VisionConfig, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(VisionConfig, "OPENAI_API_KEY", None)
    monkeypatch.setattr(VisionConfig, "GEMINI_API_KEY", None)
    monkeypatch.setattr(VisionConfig, "GROQ_API_KEY", None)


def test_factory_returns_none_without_credentials(monkeypatch):
    _clear_provider_env(monkeypatch)
    assert build_vision_client() is None


def test_factory_autodetects_openrouter(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr(VisionConfig, "OPENROUTER_API_KEY", "sk-test")
    client = build_vision_client()
    assert client is not None and client.provider == "openrouter"


def test_factory_autodetects_gemini_when_only_gemini(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr(VisionConfig, "GEMINI_API_KEY", "g-test")
    client = build_vision_client()
    assert client is not None and client.provider == "gemini"


def test_factory_explicit_provider_without_key_raises(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr(VisionConfig, "PROVIDER", "openai")
    with pytest.raises(ValueError):
        build_vision_client()


# --- Layout selector --------------------------------------------------------
def test_selector_defaults_to_docling(monkeypatch):
    monkeypatch.setattr(MinerULayoutEngine, "is_available", staticmethod(lambda: True))
    profile = _make_profile(ExtractionCost.NEEDS_LAYOUT_MODEL, math_ratio=0.0)
    engine = LayoutStrategySelector().select(profile)
    assert isinstance(engine, DoclingLayoutEngine)


def test_selector_picks_mineru_for_math_when_available(monkeypatch):
    monkeypatch.setattr(MinerULayoutEngine, "is_available", staticmethod(lambda: True))
    profile = _make_profile(ExtractionCost.NEEDS_LAYOUT_MODEL, math_ratio=0.5)
    engine = LayoutStrategySelector().select(profile)
    assert isinstance(engine, MinerULayoutEngine)


def test_selector_falls_back_to_docling_when_mineru_absent(monkeypatch):
    monkeypatch.setattr(MinerULayoutEngine, "is_available", staticmethod(lambda: False))
    profile = _make_profile(ExtractionCost.NEEDS_LAYOUT_MODEL, math_ratio=0.5)
    engine = LayoutStrategySelector().select(profile)
    assert isinstance(engine, DoclingLayoutEngine)


# --- Router -----------------------------------------------------------------
def test_router_fast_text_tier():
    engine = ExtractionRouter().get_engine(
        _make_profile(ExtractionCost.FAST_TEXT_SUFFICIENT)
    )
    assert isinstance(engine, FastTextEngine)


def test_router_layout_tier_uses_selector(monkeypatch):
    monkeypatch.setattr(MinerULayoutEngine, "is_available", staticmethod(lambda: False))
    engine = ExtractionRouter().get_engine(
        _make_profile(ExtractionCost.NEEDS_LAYOUT_MODEL)
    )
    assert isinstance(engine, DoclingLayoutEngine)


def test_router_vision_tier():
    engine = ExtractionRouter().get_engine(
        _make_profile(ExtractionCost.NEEDS_VISION_MODEL)
    )
    assert isinstance(engine, VisionAugmentedEngine)


# --- Vision engine behavior -------------------------------------------------
def test_vision_no_client_no_fallback_raises():
    engine = VisionAugmentedEngine(client=None, allow_ocr_fallback=False)
    with pytest.raises(RuntimeError):
        engine.extract("anything.pdf")


def test_vision_budget_cap_stops_before_calling(tmp_path):
    # Zero budget -> guard trips before the first call; client is never used.
    fake = _FakeClient(cost_per_call=0.5)
    engine = VisionAugmentedEngine(client=fake, budget_usd=0.0, max_pages=1)
    if not DEFAULT_SAMPLE_PDF.exists():
        pytest.skip("sample.pdf not available")
    out = engine.extract(str(DEFAULT_SAMPLE_PDF))
    assert "budget cap" in out
    assert fake.calls == 0


# --- OCR engine selection (Amharic-aware) -----------------------------------
def test_ocr_engine_explicit_tesseract(monkeypatch):
    monkeypatch.setattr(ds, "OCR_ENGINE", "tesseract")
    assert ds._select_ocr_engine() == "tesseract"


def test_ocr_engine_explicit_easyocr(monkeypatch):
    monkeypatch.setattr(ds, "OCR_ENGINE", "easyocr")
    assert ds._select_ocr_engine() == "easyocr"


def test_ocr_engine_auto_prefers_tesseract_when_installed(monkeypatch):
    monkeypatch.setattr(ds, "OCR_ENGINE", "auto")
    monkeypatch.setattr(ds, "_tesseract_available", lambda: True)
    assert ds._select_ocr_engine() == "tesseract"


def test_ocr_engine_auto_falls_back_to_easyocr(monkeypatch):
    monkeypatch.setattr(ds, "OCR_ENGINE", "auto")
    monkeypatch.setattr(ds, "_tesseract_available", lambda: False)
    assert ds._select_ocr_engine() == "easyocr"


@pytest.mark.skipif(
    not DEFAULT_SAMPLE_PDF.exists(), reason="sample.pdf not available"
)
def test_vision_vlm_path_uses_client():
    fake = _FakeClient(cost_per_call=0.0)
    engine = VisionAugmentedEngine(client=fake, budget_usd=10.0, max_pages=1)
    out = engine.extract(str(DEFAULT_SAMPLE_PDF))
    assert "Page transcription" in out
    assert fake.calls == 1
