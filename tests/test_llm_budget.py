"""Pricing, the vision budget guard and provider auto-detection (offline)."""

from __future__ import annotations

import pytest

from src.config import VisionConfig
from src.llm.budget import BudgetExceededError, BudgetGuard
from src.llm.factory import build_vision_client
from src.llm.pricing import estimate_cost


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


def _clear_provider_env(monkeypatch):
    for name in ("PROVIDER", "MODEL", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.setattr(VisionConfig, name, None)


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
