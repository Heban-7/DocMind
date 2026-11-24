"""The keyword half of hybrid search: question words to a Postgres OR-query.

``websearch_to_tsquery`` ANDs every word, so "what is the figure for
Government Bond for 2024" would only match a chunk that contains "what" and
"is" too. Here the question's quoted phrases become phrase terms, the rest of
its content words become OR terms, and ``ts_rank_cd`` ranks chunks that
match more of them first.
"""

from __future__ import annotations

import re

_STOP = set(
    """a an the and or of in on at to for from by with as is are was were be been being this that these those it its
    what which who whom whose when where why how much many does did do done has have had will would can could should
    may might must shall according figure figures value amount report reports document documents file annual page
    pages table tables about there their than then also into over under per year years total""".split()
)
# “…”, "…" and ‘…’ quote a label; a lone ' or ’ is an apostrophe ("Bank's").
_QUOTED_ALTS = re.compile(r"“([^”]{2,80})”|\"([^\"]{2,80})\"|‘([^’]{2,80})’")


class _Quoted:
    @staticmethod
    def findall(text: str) -> list[str]:
        return [next(g for g in m if g) for m in _QUOTED_ALTS.findall(text)]


_QUOTED = _Quoted()
_REFERENCE = re.compile(r"\b(Table|Note|Figure|Fig|Annex|Appendix|Schedule|Section)\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


_ALNUM = re.compile(r"[a-z]+|\d+")


def _words(text: str) -> list[str]:
    """Words, with letters and digits split apart: "EFY2017" also matches "EFY 2017"."""
    out = []
    for w in _WORD.findall(text.lower()):
        parts = _ALNUM.findall(w) if re.fullmatch(r"[a-z0-9]+", w) else [w]
        out.extend(parts if len(parts) > 1 else [w])
    return out


def _terms(text: str) -> list[str]:
    out = []
    for w in _words(text):
        if w in _STOP:
            continue
        if w.isdigit() and len(w) < 2:
            continue
        if len(w) < 3 and not w.isdigit() and not re.search(r"[ሀ-፿]", w):
            continue
        out.append(w)
    return out


def quoted_phrases(question: str) -> str:
    """The question's quoted labels as one phrase query: ``(government <-> bond) | (card <-> issuance <-> fee)``."""
    parts = []
    for phrase in _QUOTED.findall(question or ""):
        words = _words(phrase)
        if len(words) >= 2:
            parts.append("(" + " <-> ".join(words[:6]) + ")")
        elif words and len(words[0]) >= 3:
            parts.append(words[0])
    return " | ".join(dict.fromkeys(parts))


def keyword_query(question: str, max_terms: int = 16) -> str:
    """A ``to_tsquery`` string, e.g. ``(government <-> bond) | government | bond | 2024``; '' if nothing to search."""
    parts: list[str] = []
    seen: set[str] = set()
    # "Table 3", "Note 23", "Figure 2": the label of a table or note, kept as a phrase
    for kind, number in _REFERENCE.findall(question or ""):
        p = f"({kind.lower()} <-> {number})"
        if p not in seen:
            seen.add(p)
            parts.append(p)
    for phrase in _QUOTED.findall(question or ""):
        words = _words(phrase)
        if len(words) >= 2:
            p = "(" + " <-> ".join(words[:6]) + ")"
            if p not in seen:
                seen.add(p)
                parts.append(p)
    for t in _terms(question or ""):
        if t not in seen:
            seen.add(t)
            parts.append(t)
    return " | ".join(parts[:max_terms])


def keyword_overlap(question: str, text: str) -> float:
    """Share of the question's content words found in ``text`` (the in-memory stand-in)."""
    terms = set(_terms(question))
    if not terms:
        return 0.0
    words = set(_words(text or ""))
    return len(terms & words) / len(terms)
