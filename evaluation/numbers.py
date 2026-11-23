"""Number parsing and matching shared by every scorer.

Financial documents print numbers in many ways: ``1,234.5``, ``(1,234.5)``
for negatives, ``ETB 120.7 billion``, ``21.3%``. Answers add their own
variants. These helpers turn all of them into comparable floats.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SCALE_WORDS = {
    "thousand": 1e3,
    "k": 1e3,
    "million": 1e6,
    "mn": 1e6,
    "m": 1e6,
    "billion": 1e9,
    "bn": 1e9,
    "b": 1e9,
    "trillion": 1e12,
    "tn": 1e12,
}

# A number with optional thousands separators, decimals, wrapping parentheses,
# a leading minus, a trailing scale word and a percent sign.
_NUMBER_RE = re.compile(
    r"(?P<open>\()?\s*(?P<minus>[-−–])?\s*"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<close>\))?"
    r"(?:\s*(?P<pct>%|percent\b|per\s*cent\b))?"
    r"(?P<close2>\))?"
    r"(?:\s*(?P<scale>trillion|billion|million|thousand|bn|mn|tn)\b)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedNumber:
    value: float  # signed, before scale
    scale: float  # 1.0 when no scale word
    is_percent: bool
    text: str

    @property
    def absolute(self) -> float:
        return self.value * self.scale


def parse_number(text: str) -> float | None:
    """Parse one printed number: ``(1,234.5)`` -> -1234.5, ``1,234`` -> 1234."""
    s = text.strip().replace("−", "-")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    if s.startswith("-"):
        neg, s = True, s[1:].strip()
    s = s.rstrip("%").strip().replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def find_numbers(text: str) -> list[ParsedNumber]:
    """Every number in free text, with its sign, scale and percent flag."""
    out: list[ParsedNumber] = []
    for m in _NUMBER_RE.finditer(text):
        raw = m.group("num")
        v = float(raw.replace(",", ""))
        closed = bool(m.group("close") or m.group("close2"))
        negative = bool(m.group("minus")) or (bool(m.group("open")) and closed)
        scale_word = (m.group("scale") or "").lower()
        out.append(
            ParsedNumber(
                value=-v if negative else v,
                scale=_SCALE_WORDS.get(scale_word, 1.0),
                is_percent=bool(m.group("pct")),
                text=m.group(0).strip(),
            )
        )
    return out


def close_enough(a: float, b: float, rel_tol: float = 0.005, abs_tol: float = 1e-9) -> bool:
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


@dataclass(frozen=True)
class NumberMatch:
    matched: bool
    exact_scale: bool  # matched including the scale (e.g. "23 billion" vs 22,996.62 million)
    sign_ok: bool
    found: str


def match_number_in_text(
    text: str,
    gold_abs: float,
    gold_raw: float | None = None,
    *,
    is_percent: bool = False,
    rel_tol: float = 0.005,
) -> NumberMatch:
    """Does ``text`` state the gold number?

    Accepts the scaled value ("ETB 23.0 billion" for 22,996.62 million) or the
    raw printed value ("22,996.62"). Sign is checked separately so a missing
    minus sign on a "decrease of 5%" answer is reported, not hidden.
    """
    best = NumberMatch(False, False, False, "")
    for n in find_numbers(text):
        if is_percent and not (n.is_percent or n.scale == 1.0):
            continue  # "5 million" cannot answer a percentage question
        # The reverse is allowed: gold units drafted from tables are not always
        # marked as percentages (e.g. a "Loss Ratio in (%)" row), so "63.9%"
        # may answer a gold value of 63.9. Values must still match.
        for candidate, exact in ((n.absolute, True), (n.value, False)):
            target = gold_abs if exact or gold_raw is None else gold_raw
            if close_enough(abs(candidate), abs(target), rel_tol):
                sign_ok = (candidate < 0) == (target < 0) or target == 0
                m = NumberMatch(True, exact or gold_raw is None, sign_ok, n.text)
                if m.sign_ok and m.exact_scale:
                    return m
                if not best.matched:
                    best = m
    return best


# --- Presence of a printed number on an extracted page ------------------------

_TOKEN_RE = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")
_SPACE_INSIDE_NUMBER_RE = re.compile(r"(?<=[\d,.])[ \t]+(?=[\d,.])")


def normalise_number_text(text: str) -> str:
    """Canonical digits of a printed number: ``(1,234.50)`` -> ``-1234.50``."""
    s = text.strip().lstrip("~").rstrip("%").strip()
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    digits = s.strip("()-").replace(",", "").strip()
    return ("-" if neg else "") + digits


def number_tokens(text: str) -> set[str]:
    return {normalise_number_text(t).lstrip("-") for t in _TOKEN_RE.findall(text)}


def presence_on_page(value_text: str, page_text: str) -> str:
    """``intact`` / ``split`` (digits broken by spaces) / ``missing``."""
    target = normalise_number_text(value_text).lstrip("-")
    if not target:
        return "missing"
    if target in number_tokens(page_text):
        return "intact"
    collapsed = _SPACE_INSIDE_NUMBER_RE.sub("", page_text)
    if target in number_tokens(collapsed):
        return "split"
    return "missing"
