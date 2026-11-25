"""
The provider factory: "plug in whatever key you have, swap models by name".

Two ways to get a client:

* ``get_client`` / ``get_text_client`` / ``build_vision_client`` -- lenient,
  for background work (extraction, page summaries): a requested model whose
  provider has no key falls back to whatever provider is configured.
* ``client_for_request`` -- strict, for the model a user picked: the model
  must be in the registry, on the admin allow-list, and its provider's key
  must be set; otherwise ``ModelNotAvailableError`` says which of those
  failed. A user never silently gets a different model than the one shown.

Resolution for the lenient path:
  1. LLM_PROVIDER forces a provider (error if its key is missing).
  2. A requested model (arg > LLM_MODEL) is used if its provider has a key.
  3. Otherwise auto-detect by key (OpenRouter -> OpenAI -> Gemini -> Groq)
     and use that provider's default model.
  4. No key at all -> None, so the caller can fall back (local OCR, keywords).
"""

from __future__ import annotations

from src.config import VisionConfig
from src.llm import registry
from src.llm.base import LLMClient
from src.llm.errors import ModelNotAvailableError
from src.llm.providers.gemini import GeminiVisionClient
from src.llm.providers.groq import GroqVisionClient
from src.llm.providers.openai import OpenAIVisionClient
from src.llm.providers.openrouter import OpenRouterVisionClient

_AUTODETECT_ORDER = ("openrouter", "openai", "gemini", "groq")
_CLASSES = {
    "openrouter": OpenRouterVisionClient,
    "openai": OpenAIVisionClient,
    "gemini": GeminiVisionClient,
    "groq": GroqVisionClient,
}


def _key_for(provider: str) -> str | None:
    return {
        "openrouter": VisionConfig.OPENROUTER_API_KEY,
        "openai": VisionConfig.OPENAI_API_KEY,
        "gemini": VisionConfig.GEMINI_API_KEY,
        "groq": VisionConfig.GROQ_API_KEY,
    }.get(provider)


def provider_configured(provider: str) -> bool:
    return bool(_key_for(provider))


def _construct_spec(spec: registry.ModelSpec, api_key: str) -> LLMClient:
    cls = _CLASSES.get(spec.provider)
    if cls is None:
        raise ValueError(f"Unknown LLM provider '{spec.provider}'.")
    return cls(spec.slug, api_key, api_style=spec.api, reasoning_effort=spec.reasoning_effort)


def _construct(provider: str, slug: str, api_key: str) -> LLMClient:
    spec = registry.resolve(slug)
    if spec.provider != provider or not spec.known:
        spec = registry.ModelSpec(name=slug, provider=provider, slug=slug, known=False)
    return _construct_spec(spec, api_key)


def _provider_default_spec(provider: str) -> registry.ModelSpec:
    name = registry.provider_default(provider) or VisionConfig.DEFAULT_MODELS.get(provider)
    spec = registry.resolve(name) if name else None
    if spec is None or spec.provider != provider:
        raise ValueError(f"No default model is registered for provider '{provider}'.")
    return spec


def _autodetect(require_vision: bool) -> LLMClient | None:
    for provider in _AUTODETECT_ORDER:
        key = _key_for(provider)
        if not key:
            continue
        spec = _provider_default_spec(provider)
        if require_vision and not spec.supports_vision:
            continue
        return _construct_spec(spec, key)
    return None


def get_client(model: str | None = None, *, require_vision: bool = False) -> LLMClient | None:
    """Return a ready LLM client for a model name, or None if no key exists."""
    forced_provider = VisionConfig.PROVIDER
    requested = model or VisionConfig.MODEL

    if forced_provider:
        key = _key_for(forced_provider)
        if not key:
            raise ValueError(f"LLM_PROVIDER='{forced_provider}' was requested but its API key is not set.")
        spec = registry.resolve(requested) if requested else None
        if spec is None or spec.provider != forced_provider:
            # never send a foreign slug to the forced provider (it would 404)
            spec = _provider_default_spec(forced_provider)
        return _construct_spec(spec, key)

    if requested:
        spec = registry.resolve(requested)
        key = _key_for(spec.provider)
        if key and (spec.supports_vision or not require_vision):
            return _construct_spec(spec, key)

    return _autodetect(require_vision)


def build_vision_client() -> LLMClient | None:
    """A vision-capable client (the vision fallback for pages nothing else can read)."""
    return get_client(model=registry.default_model("vision"), require_vision=True)


def default_text_model() -> str | None:
    return VisionConfig.TEXT_MODEL or VisionConfig.MODEL or registry.default_model("text")


def get_text_client(model: str | None = None) -> LLMClient | None:
    """A client for text tasks, optionally for an explicit model slug/alias.

    Preference order: ``model`` -> ``LLM_TEXT_MODEL`` -> ``LLM_MODEL`` -> registry
    ``defaults.text``.
    """
    return get_client(model=model or default_text_model(), require_vision=False)


def availability(spec: registry.ModelSpec) -> tuple[bool, str]:
    """(usable, reason) for a model a user might pick."""
    if not spec.known:
        return False, "not in the model registry"
    if spec.kind != "chat":
        return False, "not a chat model"
    if not registry.is_allowed(spec):
        return False, "not on this server's allow-list" if registry.allowed_models() is not None else f"status: {spec.status}"
    forced = VisionConfig.PROVIDER
    if forced and spec.provider != forced:
        return False, f"this server is limited to {forced} models (LLM_PROVIDER)"
    if not provider_configured(spec.provider):
        return False, f"no {spec.provider} API key on this server"
    return True, ""


def client_for_request(model: str | None) -> LLMClient:
    """The client for the model a user picked (None = the server default).

    Raises:
        ModelNotAvailableError: unknown, not allowed, or no key for its provider.
        RuntimeError: no model is configured at all.
    """
    if not model:
        client = get_text_client()
        if client is None:
            raise RuntimeError(
                "No LLM is configured on this server. Set OPENAI_API_KEY (or another provider key) in .env."
            )
        return client
    spec = registry.resolve(model)
    ok, reason = availability(spec)
    if not ok:
        raise ModelNotAvailableError(f"Model '{model}' is not available: {reason}.")
    return _construct_spec(spec, _key_for(spec.provider) or "")


def catalog() -> dict:
    """What GET /api/models returns: every chat model, priced, with what it can do."""
    default = registry.resolve(default_text_model() or "").name if default_text_model() else None
    typical = _typical_tokens()
    models = []
    for name, spec in registry.all_specs().items():
        if spec.kind != "chat":
            continue
        usable, reason = availability(spec)
        models.append(
            {
                "id": name,
                "label": spec.label,
                "provider": spec.provider,
                "slug": spec.slug,
                "available": usable,
                "unavailable_reason": reason or None,
                "configured": provider_configured(spec.provider),
                "default": name == default,
                "status": spec.status,
                "price": {
                    "input_per_m": spec.input_price,
                    "cached_input_per_m": spec.cached_input_price,
                    "output_per_m": spec.output_price,
                    "currency": "USD",
                    "checked_on": registry.prices_checked_on(),
                    "source": registry.price_sources().get(spec.provider),
                    "note": spec.price_note or None,
                },
                "capabilities": {
                    "vision": spec.supports_vision,
                    "reasoning": spec.api == "reasoning",
                    "streaming": True,
                    "context_window": spec.context_window,
                },
                "free_tier": spec.free_tier,
                "data_use": spec.data_use or None,
                "tested": spec.tested,
                "benchmark": spec.benchmark or None,
                "estimate": _answer_estimate(spec, typical),
            }
        )
    models.sort(key=lambda m: (not m["available"], not m["default"], m["provider"], m["price"]["input_per_m"] or 0))
    return {
        "default": default,
        "prices_checked_on": registry.prices_checked_on(),
        "typical_answer_tokens": typical,
        "models": models,
    }


def _typical_tokens() -> dict | None:
    """Tokens of a typical answer, from the benchmarked model that measured them."""
    for spec in registry.all_specs().values():
        b = spec.benchmark or {}
        if b.get("input_tokens_mean") and b.get("output_tokens_mean"):
            return {"input": int(b["input_tokens_mean"]), "output": int(b["output_tokens_mean"]), "model": spec.name}
    return None


def _answer_estimate(spec, typical: dict | None) -> dict | None:
    """Cost of a typical answer: measured on the golden set when it was run, else from the price."""
    b = spec.benchmark or {}
    if b.get("cost_per_question_usd") is not None:
        return {"usd": float(b["cost_per_question_usd"]), "basis": "measured"}
    if typical and spec.input_price is not None and spec.output_price is not None:
        usd = (typical["input"] * spec.input_price + typical["output"] * spec.output_price) / 1e6
        return {"usd": round(usd, 6), "basis": "price"}
    return None
