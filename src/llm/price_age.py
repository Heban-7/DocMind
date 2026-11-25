"""Warn when the model prices in rubric/models.yaml are getting old.

    python -m src.llm.price_age [--max-days 90]

Prices are copied by hand from each provider's pricing page, with the date
they were checked (``prices_checked_on``). The model menu shows that date;
this check (run in CI) prints a warning once it is more than ``--max-days``
old, so a stale price is noticed before a user trusts it. It never fails the
build: an old price is a reason to look, not a broken product.
"""

from __future__ import annotations

import argparse
import os
from datetime import date


def age_in_days(checked_on: str | None, today: date | None = None) -> int | None:
    if not checked_on:
        return None
    try:
        return ((today or date.today()) - date.fromisoformat(str(checked_on)[:10])).days
    except ValueError:
        return None


def message(checked_on: str | None, max_days: int, today: date | None = None) -> str | None:
    """The warning to print, or None when the prices are recent enough."""
    days = age_in_days(checked_on, today)
    if days is None:
        return "rubric/models.yaml has no valid prices_checked_on date: check the prices and set it."
    if days > max_days:
        return (
            f"Model prices were last checked on {checked_on}, {days} days ago (more than {max_days}). "
            "Check each provider's pricing page, update rubric/models.yaml and its prices_checked_on."
        )
    return None


def main() -> None:
    from src.llm.registry import prices_checked_on

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-days", type=int, default=90)
    args = parser.parse_args()
    checked = prices_checked_on()
    warning = message(checked, args.max_days)
    if warning is None:
        print(f"Model prices checked on {checked}: {age_in_days(checked)} days ago, within {args.max_days}.")
        return
    # GitHub Actions shows ::warning:: lines as annotations on the run
    prefix = "::warning file=rubric/models.yaml::" if os.getenv("GITHUB_ACTIONS") else "WARNING: "
    print(prefix + warning)


if __name__ == "__main__":
    main()
