"""
The provider factory -- "plug in whatever you have, swap models by name".

`get_client(model=...)` is the single entry point. Resolution:
  1. If a `model` is requested (arg > LLM_MODEL), resolve it via the registry to
     a (provider, slug). If that provider's key is present, use it.
  2. If LLM_PROVIDER is forced, use exactly that provider (error if key missing).
  3. Otherwise auto-detect a provider by whichever API key is present
     (OpenRouter -> OpenAI -> Gemini -> Groq) and use its default model.
  4. If no credential exists at all, return None so the caller can fall back
     (e.g., local OCR, or keyword domain classification).

`build_vision_client()` / `get_text_client()` are thin wrappers that pick a
sensible default model for that kind of task.
"""

from __future__ import annotations

from src.config import VisionConfig
from src.llm import registry
from src.llm.base import LLMClient
from src.llm.providers.gemini import GeminiVisionClient
from src.llm.providers.groq import GroqVisionClient
from src.llm.providers.openai import OpenAIVisionClient
from src.llm.providers.openrouter import OpenRouterVisionClient

_AUTODETECT_ORDER = ("openrouter", "openai", "gemini", "groq")


def _key_for(provider: str) -> str | None:
    return {
        "openrouter": VisionConfig.OPENROUTER_API_KEY,
        "openai": VisionConfig.OPENAI_API_KEY,
        "gemini": VisionConfig.GEMINI_API_KEY,
        "groq": VisionConfig.GROQ_API_KEY,
    }.get(provider)


def _construct(provider: str, slug: str, api_key: str) -> LLMClient:
    if provider == "openrouter":
        return OpenRouterVisionClient(slug, api_key)
    if provider == "openai":
        return OpenAIVisionClient(slug, api_key)
    if provider == "gemini":
        return GeminiVisionClient(slug, api_key)
    if provider == "groq":
        return GroqVisionClient(slug, api_key)
    raise ValueError(f"Unknown LLM provider '{provider}'.")


def _autodetect(require_vision: bool) -> LLMClient | None:
    for provider in _AUTODETECT_ORDER:
        key = _key_for(provider)
        if not key:
            continue
        spec = registry.resolve(VisionConfig.DEFAULT_MODELS[provider])
        return _construct(provider, spec.slug, key)
    return None


def get_client(
    model: str | None = None, *, require_vision: bool = False
) -> LLMClient | None:
    """Return a ready LLM client for a model name, or None if no key exists."""
    forced_provider = VisionConfig.PROVIDER
    requested = model or VisionConfig.MODEL

    # (2) Explicit provider override wins.
    if forced_provider:
        key = _key_for(forced_provider)
        if not key:
            raise ValueError(
                f"LLM_PROVIDER='{forced_provider}' was requested but its API key "
                "is not set."
            )
        if requested:
            spec = registry.resolve(requested)
            if spec.provider == forced_provider:
                slug = spec.slug
            else:
                # e.g. defaults.text=gemini-flash but LLM_PROVIDER=openai:
                # never send a foreign slug to the forced provider (causes 404).
                slug = registry.resolve(
                    VisionConfig.DEFAULT_MODELS[forced_provider]
                ).slug
        else:
            slug = registry.resolve(
                VisionConfig.DEFAULT_MODELS[forced_provider]
            ).slug
        return _construct(forced_provider, slug, key)

    # (1) Honor a requested model if its provider has a key.
    if requested:
        spec = registry.resolve(requested)
        key = _key_for(spec.provider)
        if key:
            return _construct(spec.provider, spec.slug, key)
        # Requested model's provider has no key -> fall back to auto-detect.

    # (3) Auto-detect by available credential.
    return _autodetect(require_vision)


def build_vision_client() -> LLMClient | None:
    """A vision-capable client (used by Strategy C)."""
    return get_client(require_vision=True)


def get_text_client() -> LLMClient | None:
    """A cheap text client for tasks like domain classification / query agent.

    Preference order: ``LLM_TEXT_MODEL`` -> ``LLM_MODEL`` -> registry
    ``defaults.text``.
    """
    text_model = (
        VisionConfig.TEXT_MODEL
        or VisionConfig.MODEL
        or registry.default_model("text")
    )
    return get_client(model=text_model, require_vision=False)
