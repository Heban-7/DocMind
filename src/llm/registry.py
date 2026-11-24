"""
The model registry: resolves a friendly name (or raw slug) to a full spec.

Loads ``rubric/models.yaml`` once and answers what the rest of the system
needs to know about a model: which provider runs it and under which slug,
how it is called (chat or reasoning), what it costs, what it can do, whether
it has a free tier and what the provider does with prompts, and how it scored
on the golden set.

Resolution rules (in order):
  1. Friendly-name match (``gpt-4o-mini``), then an alias (``gemini-flash``).
  2. Provider-slug match (``openai/gpt-oss-120b``).
  3. Unknown name: a RAW slug. "vendor/model" means OpenRouter; anything else
     OpenAI, priced conservatively.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass, field

import yaml

from src.config import MODEL_REGISTRY_PATH

# Conservative pricing (USD / 1M tokens) for models not found in the registry.
_DEFAULT_INPUT_PRICE = 1.00
_DEFAULT_OUTPUT_PRICE = 3.00


@dataclass(frozen=True)
class ModelSpec:
    """Everything the LLM layer needs to know about one model."""

    name: str  # friendly key or raw slug
    provider: str
    slug: str
    label: str = ""
    kind: str = "chat"  # chat | embedding
    api: str = "chat"  # chat | reasoning
    reasoning_effort: str | None = None
    supports_vision: bool = False
    context_window: int | None = None
    input_price: float | None = _DEFAULT_INPUT_PRICE
    cached_input_price: float | None = None
    output_price: float | None = _DEFAULT_OUTPUT_PRICE
    price_note: str = ""
    free_tier: bool = False
    data_use: str = ""
    status: str = "current"
    tested: bool = False
    known: bool = True  # False for a raw slug that is not in the registry
    benchmark: dict = field(default_factory=dict, compare=False, hash=False)


@functools.lru_cache(maxsize=1)
def _load_registry() -> dict:
    try:
        with open(MODEL_REGISTRY_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def reload() -> None:
    """Forget the cached registry (tests, or after editing models.yaml)."""
    _load_registry.cache_clear()


def _price(entry: dict, key: str, default: float | None) -> float | None:
    if key not in entry:
        return default
    value = entry[key]
    return None if value is None else float(value)


def _spec_from_entry(name: str, entry: dict) -> ModelSpec:
    benchmarks = _load_registry().get("benchmarks", {}) or {}
    return ModelSpec(
        name=name,
        provider=entry["provider"],
        slug=entry["slug"],
        label=entry.get("label") or name,
        kind=entry.get("kind", "chat"),
        api=entry.get("api", "chat"),
        reasoning_effort=entry.get("reasoning_effort"),
        supports_vision=bool(entry.get("supports_vision", False)),
        context_window=(int(entry["context_window"]) if entry.get("context_window") else None),
        input_price=_price(entry, "input_price", _DEFAULT_INPUT_PRICE),
        cached_input_price=_price(entry, "cached_input_price", None),
        output_price=_price(entry, "output_price", _DEFAULT_OUTPUT_PRICE),
        price_note=entry.get("price_note", ""),
        free_tier=bool(entry.get("free_tier", False)),
        data_use=entry.get("data_use", ""),
        status=entry.get("status", "current"),
        tested=bool(entry.get("tested", False)),
        benchmark=dict(benchmarks.get(name) or {}),
    )


def prices_checked_on() -> str | None:
    value = _load_registry().get("prices_checked_on")
    return str(value) if value else None


def price_sources() -> dict[str, str]:
    return dict(_load_registry().get("sources") or {})


def default_model(kind: str = "text") -> str | None:
    """Friendly name of the registry default for 'text', 'vision' or 'embedding'."""
    return _load_registry().get("defaults", {}).get(kind)


def provider_default(provider: str) -> str | None:
    return (_load_registry().get("provider_defaults") or {}).get(provider)


def all_specs() -> dict[str, ModelSpec]:
    models = _load_registry().get("models", {})
    return {name: _spec_from_entry(name, entry) for name, entry in models.items()}


def resolve(name: str) -> ModelSpec:
    """Resolve a friendly name, alias or raw slug to a ModelSpec (never raises)."""
    reg = _load_registry()
    models = reg.get("models", {})
    aliases = reg.get("aliases", {}) or {}

    if name in models:
        return _spec_from_entry(name, models[name])
    if name in aliases and aliases[name] in models:
        return _spec_from_entry(aliases[name], models[aliases[name]])
    for key, entry in models.items():
        if entry.get("slug") == name:
            return _spec_from_entry(key, entry)

    provider = "openrouter" if "/" in name else "openai"
    return ModelSpec(name=name, provider=provider, slug=name, label=name, known=False)


def price_for(model: str) -> tuple[float, float]:
    """(input_price, output_price) per 1M tokens for a model name/slug."""
    spec = resolve(model)
    return (
        spec.input_price if spec.input_price is not None else _DEFAULT_INPUT_PRICE,
        spec.output_price if spec.output_price is not None else _DEFAULT_OUTPUT_PRICE,
    )


def allowed_models() -> set[str] | None:
    """The admin allow-list (``DOCMIND_ALLOWED_MODELS``, comma-separated); None = every current model."""
    raw = os.getenv("DOCMIND_ALLOWED_MODELS", "").strip()
    if not raw:
        return None
    return {resolve(n.strip()).name for n in raw.split(",") if n.strip()}


def is_allowed(spec: ModelSpec) -> bool:
    if spec.kind != "chat" or not spec.known:
        return False
    allow = allowed_models()
    if allow is None:
        return spec.status == "current"
    return spec.name in allow
