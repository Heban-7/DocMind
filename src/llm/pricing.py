"""
Token->USD pricing, used by the budget guard's estimates.

Prices now live in the model registry (rubric/models.yaml) so there is ONE
source of truth. This module is a thin convenience wrapper kept for backwards
compatibility with existing callers/tests.
"""

from __future__ import annotations

from src.llm.registry import price_for


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the USD cost of a call from its token usage."""
    in_rate, out_rate = price_for(model)
    return (input_tokens / 1_000_000) * in_rate + (
        output_tokens / 1_000_000
    ) * out_rate
