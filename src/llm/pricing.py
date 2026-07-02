"""
Rough token->USD pricing, used only for the budget guard's estimates.

These are approximate published rates (USD per 1 million tokens). They do not
need to be exact -- they exist so the BudgetGuard can stop a runaway document
before it spends real money. Unknown models fall back to a conservative rate.
"""

from __future__ import annotations

# (input_per_million, output_per_million) in USD.
_PRICING: dict[str, tuple[float, float]] = {
    "google/gemini-2.0-flash-001": (0.10, 0.40),
    "gemini-2.0-flash": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

# Used when a model is not in the table above.
_DEFAULT_RATE = (1.00, 3.00)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the USD cost of a call from its token usage."""
    in_rate, out_rate = _PRICING.get(model, _DEFAULT_RATE)
    return (input_tokens / 1_000_000) * in_rate + (
        output_tokens / 1_000_000
    ) * out_rate
