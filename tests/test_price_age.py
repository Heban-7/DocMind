"""The CI warning for model prices copied by hand."""

from __future__ import annotations


def test_price_age_warns_after_ninety_days():
    from datetime import date

    from src.llm.price_age import message

    assert message("2026-11-24", 90, today=date(2027, 2, 1)) is None
    assert "96 days ago" in message("2026-11-24", 90, today=date(2027, 2, 28))
    assert "no valid" in message(None, 90)
