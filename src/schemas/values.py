"""Reading and comparing field values: money with scale and sign, dates, codes, names.

Used by the extractor (to normalise what the model copied and to check it
against the cited cell) and by the benchmark (to compare with the answers).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from src.facts.numbers import parse_cell, scale_and_currency

_CURRENCIES = {
    "etb": "ETB", "birr": "ETB", "br": "ETB", "br.": "ETB", "ethiopian birr": "ETB", "ብር": "ETB",
    "usd": "USD", "us$": "USD", "$": "USD", "us dollars": "USD", "dollar": "USD", "dollars": "USD",
    "eur": "EUR", "€": "EUR", "euro": "EUR", "gbp": "GBP", "£": "GBP",
}


def norm_text(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[“”\"'’`]", "", s)
    return re.sub(r"[^\w]+", " ", s).strip()


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def currency_code(s: str | None) -> str | None:
    # letters only: "Birr'000" -> "birr", "ETB 1,234" -> "etb"
    t = re.sub(r"\s+", " ", re.sub(r"[^a-zሀ-፿$€£ ]+", " ", unicodedata.normalize("NFKC", s or "").lower())).strip()
    for k in sorted(_CURRENCIES, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", t) or (k in ("$", "€", "£") and k in (s or "")):
            return _CURRENCIES[k]
    up = (s or "").strip().upper()
    return up if re.fullmatch(r"[A-Z]{3}", up) else None


def scale_of(unit_text: str | None) -> float:
    """``"Birr'000"`` -> 1000, ``"in millions of Birr"`` -> 1e6, ``""`` -> 1."""
    if not unit_text:
        return 1.0
    t = unit_text.replace("’", "'")
    if re.search(r"(?i)(?:birr|etb|br)?\s*'\s*[0o]{3}|'000|000s|thousand", t):
        return 1e3
    scale, _cur = scale_and_currency(t)
    if scale != 1.0:
        return scale
    low = t.lower()
    if re.search(r"\bmillions?\b|\bmn\b", low):
        return 1e6
    if re.search(r"\bbillions?\b|\bbn\b", low):
        return 1e9
    return 1.0


def parse_amount(printed: str | None) -> float | None:
    """The number in a printed amount, with its sign: ``"(4,790,941)"`` -> -4790941."""
    if printed is None:
        return None
    s = str(printed).strip()
    n = parse_cell(s)
    if n is not None:
        return n.value
    neg = bool(re.match(r"^\s*[(\-−–]", s)) or s.endswith(")")
    m = re.search(r"\d[\d,  ]*(?:\.\d+)?|\.\d+", s)
    if not m:
        return None
    try:
        v = float(re.sub(r"[,  ]", "", m.group(0)))
    except ValueError:
        return None
    return -v if neg else v


_MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), start=1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})


def parse_date(s: str | None, *, dayfirst: bool = True) -> date | None:
    """Most printed dates: ``30 June 2023``, ``June 30, 2023``, ``2023-06-30``, ``30/06/2023``."""
    if not s:
        return None
    t = str(s).strip().lower().replace(",", " ").replace(".", " ")
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        y, mo, d = map(int, m.groups())
        return _safe(y, mo, d)
    m = re.search(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b", t)
    if m:
        a, b, y = map(int, m.groups())
        d, mo = (a, b) if dayfirst else (b, a)
        if mo > 12 and d <= 12:
            d, mo = mo, d
        return _safe(y, mo, d)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\s+(\d{4})\b", t)
    if m and m.group(2)[:3] in _MONTHS:
        return _safe(int(m.group(3)), _MONTHS[m.group(2)[:3]], int(m.group(1)))
    m = re.search(r"\b([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})\b", t)
    if m and m.group(1)[:3] in _MONTHS:
        return _safe(int(m.group(3)), _MONTHS[m.group(1)[:3]], int(m.group(2)))
    return None


def _safe(y: int, mo: int, d: int) -> date | None:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def same_text(a: str | None, b: str | None, *, threshold: float = 0.85) -> bool:
    """Names match when their words mostly agree ("EthSwitch S.C." ~ "EthSwitch Share Company")."""
    na, nb = norm_text(a), norm_text(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na or na.replace(" ", "") == nb.replace(" ", ""):  # "Eth Switch" = "EthSwitch"
        return True
    alias = {"sc": "share company", "s c": "share company", "plc": "private limited company", "co": "company"}
    for short, long in alias.items():
        na = re.sub(rf"\b{short}\b", long, na)
        nb = re.sub(rf"\b{short}\b", long, nb)
    wa, wb = set(na.split()), set(nb.split())
    if not wa or not wb:
        return False
    overlap = len(wa & wb) / min(len(wa), len(wb))
    return overlap >= threshold


def same_amount(a: float | None, b: float | None, *, rel: float = 0.005, abs_tol: float = 0.011) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b)))


def text_holds_amount(text: str, printed: str | None) -> bool:
    """Does ``text`` print the same digits as ``printed`` (thousands separators and OCR spacing aside)?"""
    d = digits(printed)
    if len(d) < 1:
        return False
    whole = digits(str(printed).split(".")[0]) if "." in str(printed or "") else d
    t = digits(text)
    return d in t or (len(whole) >= 3 and whole in t)


def text_holds_date(text: str, value: date | None) -> bool:
    if value is None:
        return False
    for m in re.finditer(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}", text or ""):
        if parse_date(m.group(0)) == value:
            return True
    return False
