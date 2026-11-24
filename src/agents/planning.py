"""Deciding what to look up before answering: one model call, or none.

V1 spent up to four model calls before it wrote a word: a greeting
classifier, a query rewriter, a document router and a tool planner. Now one
call does all four (``llm_plan``), and for a first question about a pinned
document a rule-based plan (``rules_plan``) can replace it, because search
always runs on the question itself and only the fact lookup needs a plan.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from src.agents.json_util import extract_json
from src.llm.base import LLMClient
from src.models.intent import CorpusDocument
from src.query.question import without_source

logger = logging.getLogger("docmind.planning")

GREETING = re.compile(
    r"^\s*(h(i|ello|ey|owdy)|good\s*(morning|afternoon|evening|day)|thanks?(\s+you)?(\s+so\s+much)?|thank\s*you|"
    r"bye|goodbye|see\s*you|cheers|what'?s\s*up|yo|sup|greetings|ok(ay)?|great|nice|cool|selam|ሰላም|አመሰግናለሁ)"
    r"[!.,?\s]*$",
    re.IGNORECASE,
)

_PERIOD = re.compile(
    r"""(?:FY\s*)?(?<!\d)(?:19|20)\d{2}\s*[/\-–]\s*(?:\d{4}|\d{2})(?!\d)
    |(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:EFY\s*)?(?:19|20)\d{2}
    |(?:EFY\s*)?(?<!\d)(?:19|20)\d{2}(?:\s*E\.?C\.?)?(?!\d)""",
    re.IGNORECASE | re.VERBOSE,
)
_CHANGE_PCT = re.compile(
    r"by\s+what\s+percent|percent(?:age)?\s+(?:change|increase|decrease|growth|rise|fall|decline)|growth\s+rate|"
    r"how\s+much\s+did\s+.*\s+(?:grow|increase|decrease|change)\s+in\s+percent",
    re.IGNORECASE,
)
_CHANGE_ABS = re.compile(r"how\s+much\s+(?:did|has|had)\s+.+?\s+(?:increase|decrease|change|grow|fall|rise)|difference\s+between", re.IGNORECASE)
_NUMERIC = re.compile(
    r"how\s+(?:much|many)|what\s+(?:is|was|were|are)\s+the\s+(?:figure|amount|value|number|total|rate|share|level|balance|cost|price|budget)|"
    r"figure\s+for|what\s+percent|\brate\b|\bratio\b|\bamount\b|\bvalue\b|\btotal\b|\bbudget\b|\brevenue|\bprofit|\bincome|"
    r"\bexpen|\bcost|\bassets?\b|\bliabilit|\bdeposits?\b|\bloans?\b|\bcapital\b|\bcount\b|\bnumber\s+of\b|ብር|በጀት",
    re.IGNORECASE,
)
_QUOTED = re.compile(r"“([^”]{2,80})”|\"([^\"]{2,80})\"|‘([^’]{2,80})’")
_STOP = set(
    """a an the and or of in on at to for from by with as is are was were be been this that these those it its what which
    who whom when where why how much many does did do has have had will would can could should may according figure
    figures value amount report reports document file page table year years ended period during reported report's
    percentage percent change changed increase increased decrease decreased grow grew growth between there
    their than then also into over under per by what show shows shown stated state states give""".split()
)


@dataclass
class Plan:
    kind: str = "question"  # question | chitchat
    question: str = ""
    document_id: str | None = None
    facts: dict | None = None
    section: str | None = None
    source: str = "rules"  # llm | rules | fallback
    notes: list[str] = field(default_factory=list)


def periods_in(text: str) -> list[str]:
    return list(dict.fromkeys(re.sub(r"\s+", " ", m.group(0)).strip() for m in _PERIOD.finditer(text or "")))


_FROM_TO = re.compile(r"\bfrom\s+(?:the\s+)?(?:year\s+ended\s+|fiscal\s+year\s+|budget\s+year\s+|FY\s*)?(.+?)\s+to\s+(?:the\s+)?(?:year\s+ended\s+|fiscal\s+year\s+|budget\s+year\s+|FY\s*)?(.+?)(?:[,?.]|$)", re.IGNORECASE)
_POSSESSIVE_NAME = re.compile(r"\b(?:the\s+)?(?:[A-Z][\w&.\-]*\s+(?:(?:of|and|for)\s+)?){0,6}[A-Z][\w&.\-]*['’]s\s+")



_DAY_MONTH_YEAR = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)


def _change_periods(q: str) -> list[str]:
    """``from 2022/23 to 2023/24`` -> both periods, in that order.

    A year-end date ("30 June 2023") becomes its year: statement columns print
    it many ways ("30 June 2023", "30June2023", "2023").
    """
    q = _DAY_MONTH_YEAR.sub(r"\1", q)
    m = _FROM_TO.search(q)
    if m:
        a, b = periods_in(m.group(1)), periods_in(m.group(2))
        if a and b:
            return [a[-1], b[0]]
    return periods_in(q)[:2]


def _metric_words(question: str) -> str:
    quoted = [next(g for g in m if g) for m in _QUOTED.findall(question)]
    if quoted:
        return quoted[0]
    q = _POSSESSIVE_NAME.sub(" ", without_source(question))  # "Ethio Telecom's profit" -> "profit"
    q = _PERIOD.sub(" ", q)
    words = [w for w in re.findall(r"[^\W_]+", q) if w.lower() not in _STOP and not w.isdigit()]
    return " ".join(list(dict.fromkeys(words))[:8])


def rules_plan(question: str) -> Plan:
    """A plan without a model call: search the question; look facts up when it asks for a number."""
    q = (question or "").strip()
    if GREETING.match(q):
        return Plan(kind="chitchat", question=q, source="rules")
    facts = None
    body = without_source(q)
    periods = _change_periods(body)
    metric = _metric_words(q)
    if metric:
        if _CHANGE_PCT.search(q) and len(periods) >= 2:
            facts = {"op": "percent_change", "metric": metric, "periods": periods[:2]}
        elif _CHANGE_ABS.search(q) and len(periods) >= 2:
            facts = {"op": "difference", "metric": metric, "periods": periods[:2]}
        elif _NUMERIC.search(q):
            facts = {"op": "lookup", "metric": metric, "periods": periods[:2]}
    return Plan(kind="question", question=q, facts=facts, source="rules")


def _catalog_block(docs: list[CorpusDocument], limit: int = 40) -> str:
    lines = []
    for d in docs[:limit]:
        bits = [f"id={d.document_id}", f"name={d.document_name}"]
        if d.page_count:
            bits.append(f"pages={d.page_count}")
        lines.append("- " + ", ".join(bits))
    return "\n".join(lines)


def plan_user_prompt(question: str, *, history: str = "", catalog: list[CorpusDocument] | None = None) -> str:
    parts = []
    if catalog:
        parts.append("catalog (documents the user can search):\n" + _catalog_block(catalog))
    if history.strip():
        parts.append("recent conversation:\n" + history)
    parts.append("latest message:\n" + question)
    parts.append("Return the JSON plan now.")
    return "\n\n".join(parts)


def parse_plan(payload: dict, question: str, *, catalog_ids: set[str] | None = None) -> Plan:
    kind = str(payload.get("kind") or "question").strip().lower()
    kind = "chitchat" if kind == "chitchat" else "question"
    standalone = str(payload.get("question") or "").strip() or question
    if len(standalone) > 2 * len(question) + 400:  # a plan never needs to be longer than that
        standalone = question
    doc = payload.get("document_id")
    doc = str(doc).strip() if doc not in (None, "", "null", "None") else None
    if doc and (catalog_ids is None or doc not in catalog_ids):
        doc = None
    facts = payload.get("facts")
    if not isinstance(facts, dict) or not str(facts.get("metric") or "").strip():
        facts = None
    else:
        facts = {
            k: facts[k]
            for k in ("op", "metric", "periods", "column", "unit")
            if facts.get(k) not in (None, "", [])
        }
        facts["limit"] = 10
    section = str(payload.get("section") or "").strip() or None
    return Plan(kind=kind, question=standalone, document_id=doc, facts=facts, section=section, source="llm")


def llm_plan(
    llm: LLMClient,
    question: str,
    *,
    system: str,
    history: str = "",
    catalog: list[CorpusDocument] | None = None,
) -> Plan:
    """One model call: chitchat or question, the standalone question, the document, the fact lookup."""
    result = llm.complete(
        plan_user_prompt(question, history=history, catalog=catalog),
        system=system,
        response_format="json",
        temperature=0.0,
        max_tokens=300,
    )
    payload = extract_json(result.text)
    if not isinstance(payload, dict) or not payload:
        plan = rules_plan(question)
        plan.source = "fallback"
        plan.notes.append("the planner returned no usable JSON")
        return plan
    ids = {d.document_id for d in catalog} if catalog else set()
    return parse_plan(payload, question, catalog_ids=ids)
