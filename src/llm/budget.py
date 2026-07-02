"""
The Budget Guard.

Tracks estimated spend across a single document's vision calls and refuses to
continue once a configurable cap is reached. This is the safety valve that
prevents one pathological document from burning the whole budget.
"""

from __future__ import annotations


class BudgetExceededError(RuntimeError):
    """Raised when a document would exceed its configured spend cap."""


class BudgetGuard:
    """Accumulates estimated cost and enforces a hard per-document ceiling."""

    def __init__(self, max_usd: float):
        self.max_usd = max_usd
        self.spent_usd = 0.0
        self.calls = 0

    def assert_can_spend(self) -> None:
        """Raise if we have already hit the cap (checked BEFORE each call)."""
        if self.spent_usd >= self.max_usd:
            raise BudgetExceededError(
                f"Document budget of ${self.max_usd:.2f} reached "
                f"(spent ${self.spent_usd:.4f} over {self.calls} calls)."
            )

    def record(self, cost_usd: float) -> None:
        """Add the cost of a completed call to the running total."""
        self.spent_usd += cost_usd
        self.calls += 1
