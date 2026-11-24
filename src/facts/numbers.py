"""Reading printed numbers exactly: sign, grouping, percent, scale words, currency.

    parse_cell("(1,234.5)")        -> -1234.5
    parse_cell("12.5%")            -> 12.5, percent
    parse_cell("ETB 1,845")        -> 1845, currency ETB
    find_numbers("rose by 3.2 billion birr in 2023/24") -> [3.2 x 1e9, ETB]

The V1 extractor matched ``\\d{1,3}(?:,\\d{3})*`` first, so 1845 was read as
184 and 12345.67 as 123, and every negative in parentheses became positive.
Here a number is read as a whole token or not at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MINUS = "-−–—"  # hyphen, minus sign, en dash, em dash

_CURRENCY = {
    "etb": "ETB",
    "birr": "ETB",
    "br": "ETB",
    "br.": "ETB",
    "usd": "USD",
    "us$": "USD",
    "$": "USD",
    "eur": "EUR",
    "€": "EUR",
    "gbp": "GBP",
    "£": "GBP",
}

_SCALE_WORDS = {
    "thousand": 1e3,
    "thousands": 1e3,
    "k": 1e3,
    "'000": 1e3,
    "000s": 1e3,
    "million": 1e6,
    "millions": 1e6,
    "mn": 1e6,
    "mln": 1e6,
    "m": 1e6,
    "billion": 1e9,
    "billions": 1e9,
    "bn": 1e9,
    "b": 1e9,
    "trillion": 1e12,
    "tn": 1e12,
}

# One printed number: optional currency, optional sign or parentheses, digits
# with thousands separators (comma, or a thin/no-break space), optional
# decimals, optional percent.
_GROUPED = r"\d{1,3}(?:[,  ]\d{3})+(?:\.\d+)?"
_PLAIN = r"\d+(?:\.\d+)?|\.\d+"
_CELL = re.compile(
    rf"""^\s*
    (?P<cur1>ETB|Birr|Br\.?|USD|US\$|\$|EUR|€|GBP|£)?\s*
    (?P<open>\()?\s*
    (?P<sign>[{_MINUS}+])?\s*
    (?P<cur2>ETB|Birr|Br\.?|USD|US\$|\$)?\s*
    (?P<num>{_GROUPED}|{_PLAIN})
    \s*(?P<pct>%|percent|per\s*cent)?
    \s*(?P<close>\))?
    \s*(?P<pct2>%)?
    \s*(?P<cur3>ETB|Birr|Br\.?|USD)?
    \s*(?P<foot>\*{{1,3}}|[a-z]\)|\[\d+\])?
    \s*$""",
    re.IGNORECASE | re.VERBOSE,
)

_IN_TEXT = re.compile(
    rf"""(?<![\w.,])
    (?P<cur1>ETB|Birr|Br\.|USD|US\$|\$|EUR|€)?\s?
    (?P<open>\()?
    (?P<sign>[{_MINUS}])?
    (?P<num>{_GROUPED}|\d+(?:\.\d+)?)
    (?P<close>\))?
    (?:\s?(?P<pct>%|percent|per\s*cent))?
    (?:\s?(?P<scale>thousand|million|billion|trillion|mn|bn|tn)\b)?
    (?:\s?(?P<cur3>ETB|Birr|USD|dollars?))?
    (?![\w])""",
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class Number:
    value: float  # signed, as printed, before scale
    text: str  # the exact printed span
    percent: bool = False
    currency: str = ""
    scale: float = 1.0  # from a scale word next to the number ("3.2 billion")
    start: int = 0
    end: int = 0

    @property
    def absolute(self) -> float:
        return self.value * self.scale


def _currency(*tokens: str | None) -> str:
    for t in tokens:
        if not t:
            continue
        key = t.strip().lower()
        if key.startswith("dollar"):
            return "USD"
        if key in _CURRENCY:
            return _CURRENCY[key]
    return ""


def _to_float(num: str) -> float:
    return float(num.replace(",", "").replace(" ", "").replace(" ", ""))


def parse_cell(text: str) -> Number | None:
    """Parse a table cell that holds exactly one number (else None)."""
    if not text or not text.strip():
        return None
    m = _CELL.match(text)
    if not m:
        return None
    if m.group("open") and not m.group("close") or m.group("close") and not m.group("open"):
        return None
    try:
        v = _to_float(m.group("num"))
    except ValueError:
        return None
    sign = m.group("sign") or ""
    negative = bool(m.group("open")) or (sign != "" and sign != "+")
    return Number(
        value=-v if negative else v,
        text=text.strip(),
        percent=bool(m.group("pct") or m.group("pct2")),
        currency=_currency(m.group("cur1"), m.group("cur2"), m.group("cur3")),
    )


def find_numbers(text: str) -> list[Number]:
    """Every number in running text, with sign, percent, scale word and currency."""
    out: list[Number] = []
    # Digits inside a period ("FY 2020/21", "August EFY2016") are not values.
    taken = [(p.start(), p.end()) for p in _PERIOD.finditer(text)]
    for m in _IN_TEXT.finditer(text):
        if any(a <= m.start("num") < b for a, b in taken):
            continue
        num = m.group("num")
        if m.group("open") and not m.group("close"):
            negative = bool(m.group("sign"))
        else:
            negative = bool(m.group("sign")) or bool(m.group("open") and m.group("close"))
        try:
            v = _to_float(num)
        except ValueError:
            continue
        scale_word = (m.group("scale") or "").lower()
        out.append(
            Number(
                value=-v if negative else v,
                text=m.group(0).strip(),
                percent=bool(m.group("pct")),
                currency=_currency(m.group("cur1"), m.group("cur3")),
                scale=_SCALE_WORDS.get(scale_word, 1.0),
                start=m.start("num"),
                end=m.end(),
            )
        )
    return out


# --- Scale and unit stated around a table -------------------------------------

_SCALE_PHRASE = re.compile(
    r"""(?:in|amounts?\s+in|figures?\s+in|values?\s+in|\()\s*
        (?:(?P<cur_a>ETB|Birr|Br\.?|USD|US\$|\$)\s*)?
        (?P<scale>'?000s?|thousands?|millions?|billions?|mn|bn|mln)
        (?:\s+(?:of\s+)?(?P<cur_b>ETB|Birr|Br|USD|dollars))?
    |(?P<cur_c>ETB|Birr|Br|USD)\s*(?P<scale2>'000|’000|000s|mn|bn|million|billion|thousand)
    |(?P<scale3>million|billion|thousand)\s+(?P<cur_d>birr|ETB|USD|dollars)""",
    re.IGNORECASE | re.VERBOSE,
)
_CURRENCY_WORD = re.compile(r"\b(ETB|Birr|USD|US\$)\b", re.IGNORECASE)


# OCR often reads "Birr'000" as "Birr'o0o"; Amharic tables say "በሺ ብር" (in thousand birr).
_OCR_THOUSANDS = re.compile(r"(?:ETB|Birr|Br)\s*['’`´]\s*[o0O]{2,3}\b", re.IGNORECASE)
_AMHARIC_SCALE = (("በቢሊዮን", 1e9), ("በሚሊዮን", 1e6), ("በሺ", 1e3))


def scale_and_currency(text: str) -> tuple[float, str]:
    """``("Table 4.2 (in ETB million)")`` -> ``(1e6, "ETB")``; ``(1.0, "")`` if none stated."""
    if not text:
        return 1.0, ""
    if _OCR_THOUSANDS.search(text):
        return 1e3, "ETB"
    for word, value in _AMHARIC_SCALE:
        if word in text:
            return value, "ETB" if "ብር" in text or word == "በሺ" else ""
    m = _SCALE_PHRASE.search(text)
    if not m:
        cur = _CURRENCY_WORD.search(text)
        return 1.0, (_currency(cur.group(1)) if cur else "")
    word = (m.group("scale") or m.group("scale2") or m.group("scale3") or "").lower().replace("’", "'")
    if word in ("'000", "000", "'000s", "000s"):
        scale = 1e3
    else:
        scale = _SCALE_WORDS.get(word, _SCALE_WORDS.get(word.rstrip("s"), 1.0))
    cur = m.group("cur_a") or m.group("cur_b") or m.group("cur_c") or m.group("cur_d")
    if not cur:
        c = _CURRENCY_WORD.search(text)
        cur = c.group(1) if c else ""
    return scale, _currency(cur) if cur else ""


_PERIOD = re.compile(
    r"""\b(?:FY\s*)?(?:19|20)\d{2}\s*[/\-–]\s*(?:\d{2}|\d{4})\b
    |\b(?:Q[1-4]|H[12])\s*(?:FY\s*)?(?:19|20)\d{2}\b
    |\bFY\s*(?:19|20)?\d{2}\b
    |\b(?:19|20)\d{2}\s*(?:E\.?\s?C\.?|EFY)\b
    |\b(?:EFY|E\.C\.)\s*(?:19|20)\d{2}\b
    |\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:EFY\s*)?(?:19|20)\d{2}\b
    |\b(?:19|20)\d{2}\b""",
    re.IGNORECASE | re.VERBOSE,
)


def find_period(text: str) -> str:
    """The first fiscal year, quarter, month-year or year mentioned, as printed."""
    m = _PERIOD.search(text or "")
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


def looks_like_year(n: Number) -> bool:
    return n.scale == 1.0 and not n.percent and float(n.value).is_integer() and 1900 <= n.value <= 2100 and "," not in n.text


_PERCENT_CONTEXT = re.compile(r"\(\s*%|\bin\s+(?:%|percent(?:age)?s?)\b|\bpercent(?:age)?s?\s*\)|rate\s*\(\s*%", re.IGNORECASE)


def states_percent(text: str) -> bool:
    """Does a caption or header say the figures are percentages ("Inflation Rate (%, ...)")?"""
    return bool(_PERCENT_CONTEXT.search(text or ""))
