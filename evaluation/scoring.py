"""Scorers: turn a system's raw outputs into per-item results.

Everything here is deterministic (no LLM judge), so a score never drifts
between runs and anyone can audit why an item passed or failed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from evaluation.numbers import (
    close_enough,
    match_number_in_text,
    normalise_number_text,
    parse_number,
    presence_on_page,
)
from evaluation.schema import GoldFigure, GoldQuestion, QuestionType

# --- Extraction ----------------------------------------------------------------

MIN_PAGE_CHARS = 20


@dataclass
class FigureResult:
    figure_id: str
    doc_key: str
    page: int
    on_gold_page: str  # intact | split | missing
    on_any_page: str  # intact | split | missing (anywhere in the document)
    found_on_page: int | None  # first page where it appears intact, if not the gold page
    row_intact: bool  # label and value on the same extracted line or table row
    fact_correct: bool  # the system's fact table holds the right value on that page
    fact_present: bool  # a fact with these digits exists on that page (any value)
    fact_scaled: bool = False  # ...with the right sign, scale and percent unit (M5)
    fact_typed: bool = False  # ...and labels and period that identify it (M5)

    def to_dict(self) -> dict:
        return asdict(self)


def _label_tokens(label: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-zሀ-፿]{3,}", label.lower())][:4]


def _row_intact(fig: GoldFigure, page_text: str) -> bool:
    target = normalise_number_text(fig.value_text).lstrip("-")
    tokens = _label_tokens(fig.row_label)
    if not target or not tokens:
        return False
    for line in page_text.splitlines():
        low = line.lower()
        if not all(t in low for t in tokens):
            continue
        if presence_on_page(fig.value_text, line) == "intact":
            return True
    return False


def score_figure(
    fig: GoldFigure,
    pages: dict[int, str],
    facts: list[dict],
) -> FigureResult:
    page_text = pages.get(fig.page, "")
    on_page = presence_on_page(fig.value_text, page_text)
    found_on = None
    anywhere = on_page
    if on_page != "intact":
        for p, text in sorted(pages.items()):
            state = presence_on_page(fig.value_text, text)
            if state == "intact":
                anywhere, found_on = "intact", p
                break
            if state == "split" and anywhere == "missing":
                anywhere = "split"
    target_digits = normalise_number_text(fig.value_text).lstrip("-")
    fact_present = False
    fact_correct = False
    fact_scaled = False
    fact_typed = False
    for f in facts:
        if int(f.get("page_number") or 0) != fig.page:
            continue
        vt = str(f.get("value_text") or "")
        if normalise_number_text(vt).lstrip("-") != target_digits and target_digits not in vt.replace(",", ""):
            continue
        fact_present = True
        value = f.get("value")
        if value is None or not close_enough(float(value), fig.value, 1e-6, 1e-9):
            continue
        fact_correct = True
        if "scale" not in f:  # systems before M5 had no typed facts
            break
        if abs(float(f.get("scale") or 1.0) - fig.scale) > 1e-9 or (fig.unit == "%") != (f.get("unit") == "%"):
            continue
        fact_scaled = True
        if _labels_match(fig, f):
            fact_typed = True
            break
    return FigureResult(
        figure_id=fig.figure_id,
        doc_key=fig.doc_key,
        page=fig.page,
        on_gold_page=on_page,
        on_any_page=anywhere,
        found_on_page=found_on,
        row_intact=_row_intact(fig, page_text),
        fact_correct=fact_correct,
        fact_present=fact_present,
        fact_scaled=fact_scaled,
        fact_typed=fact_typed,
    )


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zሀ-፿]{3,}|\d+", (text or "").lower()))


def _labels_match(fig: GoldFigure, fact: dict) -> bool:
    """Do the fact's labels say what the gold figure is? (half the row label's words, and the period)"""
    from src.facts.typed import normalize_period

    want = _words(fig.row_label)
    have = _words(" ".join(str(fact.get(k) or "") for k in ("row_label", "row_group", "metric", "table_title")))
    if want and len(want & have) / len(want) < 0.5:
        return False
    if fig.period or fig.column_label:
        key = normalize_period(fig.period or fig.column_label)
        keys = {fact.get("period_key") or "", normalize_period(str(fact.get("column_label") or "")),
                normalize_period(str(fact.get("period") or ""))}
        if key and key in keys:
            return True
        col = _words(fig.column_label)
        return bool(col) and col <= _words(f"{fact.get('column_label') or ''} {fact.get('period') or ''}")
    return True


def page_coverage(pages: dict[int, str], n_pages: int, failed_pages: set[int] | None = None) -> dict:
    """Pages with real content, and pages explicitly flagged as failed."""
    # Markers such as "<!-- page 3 failed: ... -->" are not content.
    with_content = {
        p for p, t in pages.items() if len(re.sub(r"\s+", "", re.sub(r"<!--.*?-->", "", t, flags=re.S))) >= MIN_PAGE_CHARS
    }
    flagged = set(failed_pages or set()) - with_content
    silent = n_pages - len(with_content) - len(flagged)
    return {
        "pages": n_pages,
        "with_content": len(with_content),
        "flagged_failed": len(flagged),
        "silently_missing": max(silent, 0),
        "accounted_ratio": (len(with_content) + len(flagged)) / n_pages if n_pages else 0.0,
        "content_ratio": len(with_content) / n_pages if n_pages else 0.0,
    }


# --- Answers -------------------------------------------------------------------

REFUSAL_MARKERS = (
    "unverifiable",
    "source not found",
    "not found",
    "could not find",
    "cannot find",
    "can't find",
    "does not contain",
    "doesn't contain",
    "no information",
    "not mentioned",
    "not provided",
    "not available in",
    "unable to find",
    "i don't know",
    "i do not know",
)


def is_refusal(answer: str) -> bool:
    low = answer.lower()
    return any(m in low for m in REFUSAL_MARKERS)


def _norm_item(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zሀ-፿0-9]{3,}", text.lower())]


def list_recall(answer: str, items: list[str]) -> float:
    if not items:
        return 0.0
    low = answer.lower()
    hit = 0
    for item in items:
        toks = _norm_item(item)
        if toks and sum(t in low for t in toks) / len(toks) >= 0.7:
            hit += 1
    return hit / len(items)


@dataclass
class AnswerResult:
    question_id: str
    doc_key: str
    qtype: str
    correct: bool
    refused: bool
    detail: str
    sign_ok: bool | None = None
    scale_ok: bool | None = None
    list_recall: float | None = None
    cited_pages: list[int] = field(default_factory=list)
    citation_precision: float | None = None  # share of citations on a gold page
    citation_hit: bool | None = None  # at least one citation on a gold page
    retrieval_hit_at_5: bool | None = None
    latency_s: float | None = None
    first_token_s: float | None = None
    llm_calls: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def score_answer(
    q: GoldQuestion,
    answer: str,
    *,
    cited_pages: list[int],
    retrieved_pages_top5: list[int] | None = None,
) -> AnswerResult:
    refused = is_refusal(answer)
    gold_pages = set(q.gold_pages)
    sign_ok = scale_ok = None
    recall = None

    if q.qtype is QuestionType.UNANSWERABLE:
        correct = refused
        detail = "refused as expected" if refused else "answered a question the document cannot answer"
    elif q.qtype is QuestionType.LIST:
        recall = list_recall(answer, q.gold_items)
        correct = recall >= 0.8 and not (refused and recall == 0)
        detail = f"list recall {recall:.0%}"
    else:
        if q.gold_value is None:
            raise ValueError(f"{q.question_id}: numeric question without gold_value")
        m = match_number_in_text(
            answer,
            q.gold_value,
            q.gold_value_raw,
            is_percent=q.gold_is_percent,
            rel_tol=q.tolerance,
        )
        sign_ok, scale_ok = (m.sign_ok, m.exact_scale) if m.matched else (None, None)
        correct = m.matched and m.sign_ok
        if m.matched and not m.sign_ok:
            detail = f"right magnitude, wrong sign ({m.found})"
        elif m.matched:
            detail = f"matched '{m.found}'"
        elif refused:
            detail = "false refusal"
        else:
            detail = "number not found in answer"

    precision = hit = None
    if cited_pages and gold_pages and q.qtype is not QuestionType.UNANSWERABLE:
        on_gold = [p for p in cited_pages if p in gold_pages]
        precision = len(on_gold) / len(cited_pages)
        hit = bool(on_gold)
    elif q.qtype is not QuestionType.UNANSWERABLE and gold_pages:
        precision, hit = 0.0, False

    retrieval_hit = None
    if retrieved_pages_top5 is not None and gold_pages:
        retrieval_hit = bool(set(retrieved_pages_top5) & gold_pages)

    return AnswerResult(
        question_id=q.question_id,
        doc_key=q.doc_key,
        qtype=q.qtype.value,
        correct=correct,
        refused=refused,
        detail=detail,
        sign_ok=sign_ok,
        scale_ok=scale_ok,
        list_recall=recall,
        cited_pages=list(cited_pages),
        citation_precision=precision,
        citation_hit=hit,
        retrieval_hit_at_5=retrieval_hit,
    )


def parse_value(value_text: str) -> float | None:
    """Re-export for drafting tools."""
    return parse_number(value_text)
