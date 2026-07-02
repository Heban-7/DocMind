"""
The model registry -- resolves a friendly name (or raw slug) to a full spec.

Loads `rubric/models.yaml` once and answers three questions the rest of the LLM
layer needs:
  * Which PROVIDER runs this model?
  * What exact SLUG does that provider expect?
  * What does it COST, and can it SEE images?

Resolution rules (in order):
  1. Exact friendly-name match in the registry (e.g. "gemini-flash").
  2. Exact provider-slug match in the registry (e.g. "gemini-2.0-flash").
  3. Unknown name: treat it as a RAW slug. If it looks like an OpenRouter slug
     ("vendor/model"), assume the openrouter provider; otherwise fall back to a
     conservative spec so the pipeline still runs (with default pricing).
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

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
    supports_vision: bool = False
    context_window: int = 0
    input_price: float = _DEFAULT_INPUT_PRICE
    output_price: float = _DEFAULT_OUTPUT_PRICE


@functools.lru_cache(maxsize=1)
def _load_registry() -> dict:
    try:
        with open(MODEL_REGISTRY_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _spec_from_entry(name: str, entry: dict) -> ModelSpec:
    return ModelSpec(
        name=name,
        provider=entry["provider"],
        slug=entry["slug"],
        supports_vision=bool(entry.get("supports_vision", False)),
        context_window=int(entry.get("context_window", 0)),
        input_price=float(entry.get("input_price", _DEFAULT_INPUT_PRICE)),
        output_price=float(entry.get("output_price", _DEFAULT_OUTPUT_PRICE)),
    )


def default_model(kind: str = "text") -> str | None:
    """Friendly name of the registry default for 'text' or 'vision'."""
    return _load_registry().get("defaults", {}).get(kind)


def all_specs() -> dict[str, ModelSpec]:
    models = _load_registry().get("models", {})
    return {name: _spec_from_entry(name, entry) for name, entry in models.items()}


def resolve(name: str) -> ModelSpec:
    """Resolve a friendly name or raw slug to a ModelSpec (never raises)."""
    models = _load_registry().get("models", {})

    # 1. Friendly-name match.
    if name in models:
        return _spec_from_entry(name, models[name])

    # 2. Provider-slug match.
    for key, entry in models.items():
        if entry.get("slug") == name:
            return _spec_from_entry(key, entry)

    # 3. Unknown -> treat as raw slug. "vendor/model" implies OpenRouter.
    provider = "openrouter" if "/" in name else "openai"
    return ModelSpec(name=name, provider=provider, slug=name)


def price_for(model: str) -> tuple[float, float]:
    """(input_price, output_price) per 1M tokens for a model name/slug."""
    spec = resolve(model)
    return (spec.input_price, spec.output_price)
