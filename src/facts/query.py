"""Numeric questions as a checked query spec; arithmetic done by the database.

The planner (an LLM) only fills in a small spec:

    {"op": "percent_change", "metric": "total revenue", "periods": ["2022/23", "2023/24"]}

The spec is validated here (allowed operations, sizes, period count) and the
Postgres store compiles it to fixed, parameterised SQL that runs under a
read-only role with a time limit and a row limit. The LLM never writes SQL
and never does arithmetic: a difference, percent change, sum or average
comes back already computed, with the cells it was computed from, so the
answer can cite them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.facts.models import FactRecord

Op = Literal["lookup", "list", "difference", "percent_change", "sum", "average", "max", "min", "count"]
CHANGE_OPS = ("difference", "percent_change")
COLUMN_OPS = ("sum", "average", "max", "min", "count")


class FactQuery(BaseModel):
    """What the planner may ask the fact table. Anything else is rejected."""

    model_config = ConfigDict(extra="ignore")

    op: Op = "lookup"
    metric: str = Field(min_length=1, max_length=200, description="what is measured, in the document's words")
    periods: list[str] = Field(default_factory=list, max_length=6, description="fiscal years, months; from -> to for changes")
    column: str | None = Field(default=None, max_length=100, description="a column label that is not a period")
    unit: str | None = Field(default=None, max_length=10, description="'%' or a currency code")
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("metric")
    @classmethod
    def _metric(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        if not re.search(r"[A-Za-zሀ-፿]", v):
            raise ValueError("metric needs words")
        return v

    @field_validator("periods")
    @classmethod
    def _periods(cls, v: list[str]) -> list[str]:
        return [p.strip()[:40] for p in v if p and p.strip()]

    @model_validator(mode="after")
    def _change_needs_two_periods(self) -> "FactQuery":
        if self.op in CHANGE_OPS and len(self.periods) != 2:
            # without a from and a to period there is nothing to compare
            object.__setattr__(self, "op", "lookup")
        return self


@dataclass
class Computed:
    """A number the database computed, and how."""

    value: float
    unit: str
    formula: str
    inputs: list[str] = field(default_factory=list)  # fact ids


@dataclass
class FactQueryResult:
    spec: FactQuery
    facts: list[FactRecord]
    computed: list[Computed] = field(default_factory=list)


# --- The same semantics in Python, for the in-memory store (tests, offline demo) -----


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def search_text(f: FactRecord) -> str:
    return _norm(" ".join([f.row_group, f.metric, f.column_label, f.table_title]))


def word_similarity(query: str, text: str) -> float:
    """Roughly pg_trgm's word_similarity: how well the query matches some part of the text."""
    q, t = _norm(query), _norm(text)
    if not q or not t:
        return 0.0
    if q in t:
        return 1.0
    qt = set(re.findall(r"\w{3,}", q))
    tt = set(re.findall(r"\w{3,}", t))
    overlap = len(qt & tt) / len(qt) if qt else 0.0
    return max(overlap, SequenceMatcher(None, q, t).find_longest_match(0, len(q), 0, len(t)).size / len(q))


def period_matches(f: FactRecord, period: str) -> bool:
    from src.facts.typed import normalize_period

    key = normalize_period(period)
    if key and key == f.period_key:
        return True
    return _norm(period) in _norm(f.column_label) or (bool(f.period) and _norm(period) in _norm(f.period))


def run_in_memory(facts: list[FactRecord], spec: FactQuery, *, doc_id: str | None = None, threshold: float = 0.45) -> FactQueryResult:
    pool = [
        (word_similarity(spec.metric, search_text(f)), f)
        for f in facts
        if (doc_id is None or f.doc_id == doc_id) and f.value is not None
    ]
    pool = [(s, f) for s, f in pool if s >= threshold]
    if spec.unit:
        pool = [(s, f) for s, f in pool if f.unit == spec.unit]
    if spec.column:
        pool = [(s, f) for s, f in pool if _norm(spec.column) in _norm(f.column_label)]
    pool.sort(key=lambda t: (-t[0], -t[1].confidence, t[1].page_number))

    if spec.op in CHANGE_OPS:
        p1, p2 = spec.periods
        a_side = [(s, f) for s, f in pool if period_matches(f, p1)]
        b_side = [(s, f) for s, f in pool if period_matches(f, p2)]
        pairs = []
        for sa, a in a_side:
            for sb, b in b_side:
                same_row = a.table_id and a.table_id == b.table_id and a.row_index == b.row_index
                if a.id != b.id and a.doc_id == b.doc_id and a.unit == b.unit and (same_row or _norm(a.metric) == _norm(b.metric)):
                    pairs.append((sa + sb, a, b))
        pairs.sort(key=lambda t: -t[0])
        out = FactQueryResult(spec, [])
        for _, a, b in pairs[:3]:
            va, vb = a.absolute_value, b.absolute_value
            if spec.op == "difference":
                value, formula = vb - va, f"{p2} - {p1}"
            elif va:
                value, formula = (vb - va) / abs(va) * 100, f"({p2} - {p1}) / |{p1}| x 100"
            else:
                continue
            out.facts += [a, b]
            out.computed.append(Computed(round(value, 4), "%" if spec.op == "percent_change" else a.unit, formula, [a.id, b.id]))
        return out

    if spec.periods:
        pool = [(s, f) for s, f in pool if any(period_matches(f, p) for p in spec.periods)]
    if spec.op in COLUMN_OPS and pool:
        best = pool[0][1]
        column = [
            f for _, f in pool
            if f.table_id and f.table_id == best.table_id and f.col_index == best.col_index and "total" not in f.row_label.lower()
        ] or [best]
        column = column[: spec.limit]
        values = [f.absolute_value for f in column]
        if spec.op == "sum":
            computed = Computed(sum(values), best.unit, "sum of the column", [f.id for f in column])
        elif spec.op == "average":
            computed = Computed(sum(values) / len(values), best.unit, "average of the column", [f.id for f in column])
        elif spec.op == "count":
            computed = Computed(float(len(column)), "rows", "rows in the column", [f.id for f in column])
        else:
            pick = max(column, key=lambda f: f.absolute_value) if spec.op == "max" else min(column, key=lambda f: f.absolute_value)
            computed = Computed(pick.absolute_value, best.unit, f"{spec.op} of the column: {pick.row_label}", [pick.id])
        return FactQueryResult(spec, column, [computed])
    return FactQueryResult(spec, [f for _, f in pool[: spec.limit]])
