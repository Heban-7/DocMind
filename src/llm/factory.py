"""
The provider factory -- "plug in whatever you have".

Resolution order:
  1. If LLM_PROVIDER is set, use exactly that provider (error if its key is
     missing).
  2. Otherwise auto-detect: OpenRouter -> OpenAI -> Gemini, by whichever API key
     is present in the environment.
  3. If no credential exists at all, return None so the caller can fall back to
     local OCR.

The model defaults per-provider but can be overridden with LLM_MODEL.
"""

from __future__ import annotations

from src.config import VisionConfig
from src.llm.base import VisionLLMClient
from src.llm.providers.gemini import GeminiVisionClient
from src.llm.providers.openai import OpenAIVisionClient
from src.llm.providers.openrouter import OpenRouterVisionClient


def _key_for(provider: str) -> str | None:
    return {
        "openrouter": VisionConfig.OPENROUTER_API_KEY,
        "openai": VisionConfig.OPENAI_API_KEY,
        "gemini": VisionConfig.GEMINI_API_KEY,
    }.get(provider)


def _construct(provider: str, model: str, api_key: str) -> VisionLLMClient:
    if provider == "openrouter":
        return OpenRouterVisionClient(model, api_key)
    if provider == "openai":
        return OpenAIVisionClient(model, api_key)
    if provider == "gemini":
        return GeminiVisionClient(model, api_key)
    raise ValueError(f"Unknown LLM provider '{provider}'.")


def build_vision_client() -> VisionLLMClient | None:
    """Return a ready vision client, or None if no credential is available."""
    explicit = VisionConfig.PROVIDER

    if explicit:
        key = _key_for(explicit)
        if not key:
            raise ValueError(
                f"LLM_PROVIDER='{explicit}' was requested but its API key is not set."
            )
        model = VisionConfig.MODEL or VisionConfig.DEFAULT_MODELS[explicit]
        return _construct(explicit, model, key)

    # Auto-detect by whichever key is present.
    for provider in ("openrouter", "openai", "gemini"):
        key = _key_for(provider)
        if key:
            model = VisionConfig.MODEL or VisionConfig.DEFAULT_MODELS[provider]
            return _construct(provider, model, key)

    return None  # no credentials -> caller decides (e.g., OCR fallback)
