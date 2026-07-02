"""
Unit tests for the generalized LLM layer (Phase 3A) and the LLM-based domain
classifier with keyword fallback (Phase 3B).

All tests are offline: they exercise message translation, the registry, the
factory's provider resolution, and the classifier fallback logic with fakes.
"""

from __future__ import annotations

import pytest

from src.agents.domain import (
    FallbackDomainClassifier,
    KeywordDomainClassifier,
    LlmDomainClassifier,
    _parse_domain_json,
)
from src.config import VisionConfig
from src.llm import factory, registry
from src.llm.base import LLMClient, LLMResult
from src.llm.providers._openai_compatible import _to_openai_messages
from src.llm.providers.gemini import _to_gemini
from src.models.document_profile import DomainHint


# --- Registry ---------------------------------------------------------------
def test_registry_resolves_friendly_name():
    spec = registry.resolve("gemini-flash")
    assert spec.provider == "gemini"
    assert spec.slug == "gemini-2.0-flash"
    assert spec.supports_vision is True


def test_registry_resolves_by_slug():
    spec = registry.resolve("gpt-4o-mini")
    assert spec.provider == "openai"


def test_registry_unknown_slug_with_slash_is_openrouter():
    spec = registry.resolve("some-vendor/some-model")
    assert spec.provider == "openrouter"
    assert spec.slug == "some-vendor/some-model"


def test_registry_price_lookup():
    in_p, out_p = registry.price_for("gpt-4o-mini")
    assert (in_p, out_p) == (0.15, 0.60)


def test_registry_default_text_model():
    assert registry.default_model("text") == "gemini-flash"


# --- Message translation ----------------------------------------------------
def test_openai_translation_text_and_image():
    messages = [
        {"role": "system", "content": "be terse"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "image", "image": b"\x89PNG", "mime": "image/png"},
            ],
        },
    ]
    out = _to_openai_messages(messages)
    assert out[0] == {"role": "system", "content": "be terse"}
    parts = out[1]["content"]
    assert parts[0]["type"] == "text"
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_gemini_translation_splits_system():
    messages = [
        {"role": "system", "content": "you are X"},
        {"role": "user", "content": "hello"},
    ]
    contents, system = _to_gemini(messages)
    assert system == "you are X"
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "hello"


# --- Factory resolution -----------------------------------------------------
def _clear(monkeypatch):
    for attr in (
        "PROVIDER",
        "MODEL",
        "TEXT_MODEL",
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
    ):
        monkeypatch.setattr(VisionConfig, attr, None)


def test_get_client_none_without_keys(monkeypatch):
    _clear(monkeypatch)
    assert factory.get_client() is None


def test_get_client_honors_requested_model_provider(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setattr(VisionConfig, "OPENAI_API_KEY", "sk-openai")
    client = factory.get_client(model="gpt-4o-mini")
    assert client is not None and client.provider == "openai"
    assert client.model == "gpt-4o-mini"


def test_get_client_falls_back_when_requested_provider_has_no_key(monkeypatch):
    _clear(monkeypatch)
    # Ask for a Gemini model but only OpenRouter is configured.
    monkeypatch.setattr(VisionConfig, "OPENROUTER_API_KEY", "sk-or")
    client = factory.get_client(model="gemini-flash")
    assert client is not None and client.provider == "openrouter"


def test_get_client_forced_provider_missing_key_raises(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setattr(VisionConfig, "PROVIDER", "groq")
    with pytest.raises(ValueError):
        factory.get_client()


def test_get_client_autodetect_prefers_openrouter(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setattr(VisionConfig, "OPENROUTER_API_KEY", "sk-or")
    monkeypatch.setattr(VisionConfig, "OPENAI_API_KEY", "sk-oa")
    assert factory.get_client().provider == "openrouter"


def test_get_text_client_uses_text_default(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setattr(VisionConfig, "GEMINI_API_KEY", "g-key")
    client = factory.get_text_client()
    assert client is not None and client.provider == "gemini"


# --- Domain JSON parsing ----------------------------------------------------
def test_parse_domain_json_plain():
    assert _parse_domain_json('{"domain": "financial", "confidence": 0.9}') == (
        DomainHint.FINANCIAL,
        0.9,
    )


def test_parse_domain_json_with_code_fence():
    raw = '```json\n{"domain": "legal", "confidence": 0.7}\n```'
    assert _parse_domain_json(raw) == (DomainHint.LEGAL, 0.7)


def test_parse_domain_json_bad_returns_none():
    assert _parse_domain_json("not json at all") is None


def test_parse_domain_json_clamps_confidence():
    assert _parse_domain_json('{"domain":"medical","confidence":5}') == (
        DomainHint.MEDICAL,
        1.0,
    )


# --- Fake LLM client for classifier tests -----------------------------------
class _FakeLLM(LLMClient):
    provider = "fake"

    def __init__(self, reply: str = "", raise_exc: bool = False):
        super().__init__("fake")
        self._reply = reply
        self._raise = raise_exc

    def chat(self, messages, *, response_format=None, temperature=None, max_tokens=None):
        if self._raise:
            raise RuntimeError("boom")
        return LLMResult(text=self._reply, model=self.model, provider=self.provider)


# --- LlmDomainClassifier ----------------------------------------------------
def test_llm_classifier_parses_reply():
    clf = LlmDomainClassifier(
        client=_FakeLLM('{"domain": "financial", "confidence": 0.88}')
    )
    assert clf.classify("annual revenue report") == (DomainHint.FINANCIAL, 0.88)


def test_llm_classifier_unavailable_without_client():
    clf = LlmDomainClassifier(client=None)
    # No key in a clean env -> not available; classify returns GENERAL/0.
    if not clf.available:
        assert clf.classify("x") == (DomainHint.GENERAL, 0.0)


# --- FallbackDomainClassifier ----------------------------------------------
def test_fallback_uses_primary_when_confident():
    primary = LlmDomainClassifier(
        client=_FakeLLM('{"domain": "legal", "confidence": 0.9}')
    )
    fallback = KeywordDomainClassifier()
    clf = FallbackDomainClassifier(primary, fallback)
    assert clf.classify("some contract text")[0] == DomainHint.LEGAL


def test_fallback_uses_keyword_when_primary_errors():
    primary = LlmDomainClassifier(client=_FakeLLM(raise_exc=True))
    fallback = KeywordDomainClassifier()
    clf = FallbackDomainClassifier(primary, fallback)
    # Financial keywords should win via the fallback path.
    text = "revenue balance income assets liabilities profit fiscal audit"
    assert clf.classify(text)[0] == DomainHint.FINANCIAL


def test_fallback_uses_keyword_when_primary_low_confidence():
    primary = LlmDomainClassifier(
        client=_FakeLLM('{"domain": "medical", "confidence": 0.05}')
    )
    fallback = KeywordDomainClassifier()
    clf = FallbackDomainClassifier(primary, fallback)
    text = "revenue balance income assets liabilities profit fiscal audit"
    assert clf.classify(text)[0] == DomainHint.FINANCIAL
