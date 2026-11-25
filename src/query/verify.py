"""Check an answer against its evidence, sentence by sentence, without a model.

The answer step cites evidence ids after each sentence (``[E2]``). For every
sentence this module:

1. reads the numbers it states (sign, percent, scale words) and looks for
   each one in the evidence it cites, then in the rest of the evidence;
   a number found nowhere is *unsupported* (V1 printed an invented
   "49.5 million subscribers" with a page badge);
2. re-points the citations to the evidence that holds the sentence's
   numbers, so a badge never points at a page that does not say it
   (V1 padded every answer to five citations: precision 0.05);
3. flags a sentence that names a place, organisation or year from the
   question that no evidence mentions (the "inflation in Kenya" answers
   that quoted Ethiopia's figure).

Unsupported sentences are removed from the answer. When nothing that states
a fact is left, the answer becomes "Not found in the document".
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from src.facts.numbers import Number, find_numbers, looks_like_year

CITE = re.compile(r"\[E(\d{1,3})\]")
_CITE_RUN = re.compile(r"(?:\s*\[E\d{1,3}\])+")
# a number right after one of these words is a label, not a value ("Table 3", "Note 20")
_LABEL_BEFORE = re.compile(
    r"(?:table|note|notes|figure|fig\.|section|page|pages|program|programme|article|chapter|annex|appendix|"
    r"schedule|pillar|goal|phase|part|step|no\.|number|#|q|item|level|tier|grade|row|column|tender|"
    r"proclamation|directive|regulation)\s*$",
    re.IGNORECASE,
)
_LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+")
_ABBREVIATIONS = ("e.c.", "no.", "co.", "ltd.", "inc.", "mr.", "ms.", "dr.", "vs.", "e.g.", "i.e.", "p.", "pp.", "s.c.", "plc.", "etc.")
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"“(\[]?[A-Zሀ-፿0-9*])|\n+")
NOT_FOUND = "Not found in the document"

_QUESTION_STOP = set(
    """according what which who whom whose when where why how is are was were the a an of in on for to from by and or
    did does do has have had this that these those its their total figure report reports annual document file
    statement statements bulletin procedure year years ended period quarter month""".split()
)
_MONTHS = set("january february march april may june july august september october november december".split())


@dataclass
class SentenceCheck:
    text: str
    cited: list[int] = field(default_factory=list)  # evidence numbers as written ([E2] -> 2)
    final_cites: list[int] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    derived_numbers: list[str] = field(default_factory=list)  # changes recomputed from the sentence's own figures
    quoted_numbers: list[str] = field(default_factory=list)  # figures repeated from the question
    missing_terms: list[str] = field(default_factory=list)
    status: str = "no_claim"  # supported | unsupported | uncited | no_claim

    @property
    def kept(self) -> bool:
        return self.status != "unsupported"


@dataclass
class Verification:
    answer: str  # with [E#] markers, unsupported sentences removed
    sentences: list[SentenceCheck]
    cited: list[int]  # evidence numbers the kept sentences cite, in first-use order
    removed: int = 0
    not_found: bool = False
    missing_terms: list[str] = field(default_factory=list)
    # evidence number -> the figures (as the answer writes them) it was found to print,
    # and the kept sentences that cite it: where on the page the box goes
    evidence_numbers: dict[int, list[str]] = field(default_factory=dict)
    evidence_claims: dict[int, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        claims = [s for s in self.sentences if s.status != "no_claim"]
        return {
            "checked_sentences": len(claims),
            "supported": sum(s.status == "supported" for s in claims),
            "uncited": sum(s.status == "uncited" for s in claims),
            "removed": self.removed,
            "numbers_checked": sum(len(s.numbers) for s in self.sentences),
            "numbers_unsupported": sum(len(s.unsupported_numbers) for s in self.sentences),
            "numbers_recomputed": sum(len(s.derived_numbers) for s in self.sentences),
            "missing_terms": list(self.missing_terms),
            "not_found": self.not_found,
            "sentences": [asdict(s) | {"kept": s.kept} for s in self.sentences],
        }


# --- splitting -------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    """Sentences and list lines, keeping each sentence's trailing citations with it."""
    pieces = [p for p in _SPLIT.split(text or "") if p and p.strip()]
    out: list[str] = []
    for piece in pieces:
        # "[E3]" pushed to the start of the next piece belongs to the previous sentence
        lead = re.match(r"^((?:\s*\[E\d{1,3}\])+)\s*", piece)
        if lead and out:
            out[-1] = out[-1].rstrip() + lead.group(1)
            piece = piece[lead.end():]
            if not piece.strip():
                continue
        if out and out[-1].rstrip().lower().endswith(_ABBREVIATIONS) and "\n" not in out[-1]:
            out[-1] = out[-1].rstrip() + " " + piece.lstrip()
        else:
            out.append(piece.strip())
    return out


def strip_cites(text: str) -> str:
    return _CITE_RUN.sub("", text or "")


# --- numbers ---------------------------------------------------------------------


def _decimals(n: Number) -> int:
    m = re.search(r"\d+(?:[.,]\d+)*", n.text)
    if not m:
        return 0
    digits = m.group(0)
    if "." in digits:
        return len(digits.rsplit(".", 1)[1])
    return 0


def claim_numbers(sentence: str) -> list[Number]:
    """The values a sentence states (labels like "Table 3", years and list markers skipped)."""
    body = _LIST_MARKER.sub("", strip_cites(sentence))
    out = []
    for n in find_numbers(body):
        if looks_like_year(n):
            continue
        before = body[max(0, n.start - 14): n.start]
        if _LABEL_BEFORE.search(before.rstrip(" (")):
            continue
        out.append(n)
    return out


def derived_change(n: Number, figures: list[Number]) -> bool:
    """Is ``n`` the change between two figures the sentence states (and the evidence holds)?

    "from 9,689 to 11,760, up 21.4%": 21.4 is recomputed as (11,760 - 9,689)
    / 9,689 x 100 within the rounding the answer printed. A wrong figure fails.
    """
    if len(figures) < 2:
        return False
    target = abs(n.value) * (1.0 if n.percent else n.scale)
    tol = 0.5 * (10 ** -_decimals(n)) * (1.0 if n.percent else n.scale) + 1e-9
    values = [f.value * f.scale for f in figures if not f.percent or n.percent]
    for i, a in enumerate(values):
        for j, b in enumerate(values):
            if i == j:
                continue
            if n.percent:
                if a and abs(abs((b - a) / abs(a) * 100) - target) <= max(tol, 0.051):
                    return True
            elif abs(abs(b - a) - target) <= max(tol, abs(target) * 5e-4):
                return True
    return False


class EvidenceNumbers:
    """The numbers of one evidence item, ready for matching."""

    def __init__(self, text: str, extra_values: list[float] | None = None):
        self.values: list[tuple[float, bool]] = []  # (absolute value, is percent)
        for n in find_numbers(text or ""):
            self.values.append((abs(n.value) * n.scale, n.percent))
            if n.scale != 1.0:
                self.values.append((abs(n.value), n.percent))
        for v in extra_values or []:
            if v is not None:
                self.values.append((abs(float(v)), False))

    def holds(self, n: Number) -> bool:
        answer = abs(n.value) * n.scale
        tol = 0.5 * (10 ** -_decimals(n)) * n.scale
        for value, _pct in self.values:
            if n.percent:
                if abs(answer - value) <= tol + 1e-9 or abs(answer - value) <= abs(value) * 5e-4:
                    return True
                continue
            # tables print "73,270" under "(ETB million)"; prose says "ETB 73.27 billion"
            for shift in (1.0, 1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9):
                c = value * shift
                if abs(answer - c) <= tol * (1 + 1e-9) or (c and abs(answer - c) <= abs(c) * 5e-4):
                    return True
        return False


# --- scope terms -------------------------------------------------------------------


_QUOTED_LABEL = re.compile(r"“[^”]*”|\"[^\"]*\"|‘[^’]*’")


def _stem(word: str) -> str:
    w = word.lower().strip("'’")
    for suffix in ("'s", "’s", "ies", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return w


def scope_terms(question: str) -> list[str]:
    """Names and years the question is about: "kenya", "2014", "telecom" (lower-case stems).

    Quoted labels ("Profit After Tax") are left to retrieval, and acronyms
    (IFRS, CBE) are not used: documents often spell them out.
    """
    from src.query.question import without_source

    # the question's name for its own document ("According to the CBE Annual
    # Report 2023-24") is not something the evidence has to repeat
    q = _QUOTED_LABEL.sub(" ", without_source(question or ""))
    terms: list[str] = []
    for m in re.finditer(r"(?<!\d)(?:19|20)\d{2}(?!\d)", q):
        terms.append(m.group(0))
    words = re.findall(r"[A-Za-z][A-Za-z'’\-]+", q)
    for i, w in enumerate(words):
        if not w[0].isupper() or w.removesuffix("'s").removesuffix("’s").isupper():  # "CBE's" is an acronym too
            continue
        stem = _stem(w)
        if i == 0 or stem in _QUESTION_STOP or stem in _MONTHS or len(stem) < 3:
            continue
        terms.append(stem)
    return list(dict.fromkeys(terms))


def as_written(question: str, term: str) -> str:
    """The question's own spelling of a scope term ("kenya" -> "Kenya")."""
    for w in re.findall(r"[A-Za-z][A-Za-z'’\-]+|\d{4}", question or ""):
        if _stem(w) == term or w == term:
            return w.removesuffix("'s").removesuffix("’s")
    return term


def missing_scope_terms(question: str, corpus_text: str) -> list[str]:
    """The question's names and years that no evidence (or document title) mentions.

    When the evidence is largely Amharic, an English name may well be there
    in Ge'ez script, so only years are checked.
    """
    low = (corpus_text or "").lower()
    letters = re.findall(r"[^\W\d_]", low)
    ethiopic = sum(1 for ch in letters if "ሀ" <= ch <= "፿")
    mostly_ethiopic = bool(letters) and ethiopic / len(letters) > 0.2
    return [t for t in scope_terms(question) if t not in low and (t.isdigit() or not mostly_ethiopic)]


# --- the check ---------------------------------------------------------------------


def verify_answer(
    answer: str,
    evidence: list[str],
    *,
    question: str = "",
    evidence_values: list[list[float]] | None = None,
    titles: str = "",
    strict: bool = False,
) -> Verification:
    """Check every sentence of ``answer`` (citations ``[E1]`` = ``evidence[0]``).

    ``strict`` (Audit Mode) also removes sentences that state a fact without
    citing any evidence.
    """
    numbers = [EvidenceNumbers(t, (evidence_values or [None] * len(evidence))[i] if evidence_values else None) for i, t in enumerate(evidence)]
    corpus = " ".join(evidence) + " " + (titles or "")
    missing = missing_scope_terms(question, corpus)
    # a figure the user wrote (a claim to check, "is it ETB 9 billion?") may be repeated
    asked = EvidenceNumbers(question or "")
    checks: list[SentenceCheck] = []
    held: list[dict[int, list[str]]] = []  # per sentence: evidence number -> its figures
    refusal = (answer or "").strip().lower().startswith(NOT_FOUND.lower())

    for sentence in split_sentences(answer):
        cited = [int(x) for x in CITE.findall(sentence)]
        valid = [c for c in cited if 1 <= c <= len(evidence)]
        check = SentenceCheck(text=sentence, cited=cited)
        nums = claim_numbers(sentence)
        check.numbers = [n.text for n in nums]
        low = strip_cites(sentence).lower()
        check.missing_terms = [t for t in missing if re.search(rf"(?<![\w]){re.escape(t)}", low)]
        where: dict[int, list[str]] = {}
        held.append(where)

        if nums:
            supporting: list[int] = []
            found: list[Number] = []
            not_found: list[Number] = []
            for n in nums:
                own = [c for c in valid if numbers[c - 1].holds(n)]
                if own:
                    supporting += own
                    found.append(n)
                    if not _in_date(body_of(sentence), n):
                        for c in own:
                            where.setdefault(c, []).append(n.text)
                    continue
                elsewhere = [i + 1 for i, ev in enumerate(numbers) if ev.holds(n)]
                if elsewhere:
                    supporting.append(elsewhere[0])
                    found.append(n)
                    if not _in_date(body_of(sentence), n):
                        where.setdefault(elsewhere[0], []).append(n.text)
                else:
                    not_found.append(n)
            for n in not_found:
                # a change the sentence derives from two figures it states: recompute it
                if derived_change(n, found):
                    check.derived_numbers.append(n.text)
                elif asked.holds(n):
                    check.quoted_numbers.append(n.text)
                else:
                    check.unsupported_numbers.append(n.text)
            check.final_cites = list(dict.fromkeys(supporting))
            check.status = "unsupported" if check.unsupported_numbers else "supported"
        elif valid:
            check.final_cites = list(dict.fromkeys(valid))
            check.status = "supported"
        elif _states_fact(sentence) and not low.startswith(NOT_FOUND.lower()):
            check.status = "unsupported" if strict else "uncited"
        if check.missing_terms and not low.startswith(NOT_FOUND.lower()) and check.status != "no_claim":
            check.status = "unsupported"
        checks.append(check)

    kept = [c for c in checks if c.kept]
    removed = len(checks) - len(kept)
    facts_left = any(c.status == "supported" for c in kept)
    not_found = refusal or not facts_left
    if not_found and not refusal:
        reason = ", ".join(missing) if missing else "a statement the evidence supports"
        text = f"{NOT_FOUND}: I could not find {reason} in the evidence for this question."
        if missing:
            text = f"{NOT_FOUND}: the document does not mention {', '.join(m.title() if not m.isdigit() else m for m in missing)}."
        kept_text = text
        cited: list[int] = []
    else:
        kept_text = _rebuild(answer, checks)
        cited = list(dict.fromkeys(c for s in kept for c in s.final_cites))
    ev_numbers: dict[int, list[str]] = {}
    ev_claims: dict[int, list[str]] = {}
    if not not_found:
        for check, where in zip(checks, held):
            if not check.kept:
                continue
            for c, texts in where.items():
                ev_numbers.setdefault(c, []).extend(t for t in texts if t not in ev_numbers.get(c, []))
            for c in check.final_cites:
                ev_claims.setdefault(c, []).append(strip_cites(check.text).strip())
    return Verification(
        answer=kept_text, sentences=checks, cited=cited, removed=removed, not_found=not_found, missing_terms=missing,
        evidence_numbers=ev_numbers, evidence_claims=ev_claims,
    )


def body_of(sentence: str) -> str:
    """The text ``claim_numbers`` reads positions from."""
    return _LIST_MARKER.sub("", strip_cites(sentence))


_MONTH_WORD = re.compile(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b\.?", re.IGNORECASE)


def _in_date(body: str, n: Number) -> bool:
    """Is ``n`` the day of a date ("30 June 2017", "June 30, 2017")?"""
    if n.percent or n.scale != 1.0 or not (1 <= abs(n.value) <= 31) or n.value != int(n.value):
        return False
    near = body[max(0, n.start - 11): n.start] + " " + body[n.end: n.end + 11]
    return bool(_MONTH_WORD.search(near))


def _states_fact(sentence: str) -> bool:
    body = strip_cites(sentence).strip()
    if len(body) < 25 or body.endswith("?") or body.endswith(":"):
        return False
    return True


def _rebuild(answer: str, checks: list[SentenceCheck]) -> str:
    """The answer without its unsupported sentences, citations re-pointed."""
    out = answer
    for c in checks:
        if not c.kept:
            out = out.replace(c.text, "", 1)
        elif c.final_cites and c.final_cites != [x for x in dict.fromkeys(c.cited)]:
            body = _CITE_RUN.sub("", c.text).rstrip()
            trail = ""
            if body and body[-1] in ".!?;:":
                body, trail = body[:-1], body[-1]
            marks = "".join(f"[E{i}]" for i in c.final_cites)
            out = out.replace(c.text, f"{body} {marks}{trail}", 1)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()
