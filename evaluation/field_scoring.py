"""Scoring schema fields against the answers: precision, recall, F1, and the review queue's worth.

A field counts once per document. A value the extractor gives is right when
it matches the answer (or an accepted alternative):

    money, number  within 0.5% (statements round; scale errors are 1000x off)
    date, code     equal after normalising (2023-06-30, ETB)
    text           names: most words in common; numbers and ids: the same characters

A wrong value counts against both precision and recall (it is a wrong
prediction AND a missed answer). Line items count once per line: a line is
right when its amount, quantity and unit price match a line of the answer.

The review queue is scored too: of the wrong values, how many did the
extractor send to review ("errors flagged"); of the values it accepted
without review, how many are right ("auto precision").
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from src.schemas import values as V
from src.schemas.schema import get_schema

_ID_LIKE = re.compile(r"(number|tin|_id|code)$")


def _match(kind: str, name: str, got, want) -> bool:
    if got is None or want is None:
        return False
    if kind in ("money", "number"):
        try:
            return V.same_amount(float(got), float(want))
        except (TypeError, ValueError):
            return False
    if kind in ("date", "code"):
        if kind == "code":
            return (V.currency_code(str(got)) or str(got).upper()) == (V.currency_code(str(want)) or str(want).upper())
        return str(got)[:10] == str(want)[:10]
    if _ID_LIKE.search(name):
        return re.sub(r"[\s\-_/.]", "", str(got)).upper() == re.sub(r"[\s\-_/.]", "", str(want)).upper()
    return V.same_text(str(got), str(want))


def _match_items(got: list[dict], want: list[dict], cols: dict) -> int:
    """How many answer lines have a matching extracted line (each used once)."""
    used: set[int] = set()
    hits = 0
    for w in want:
        for i, g in enumerate(got):
            if i in used:
                continue
            ok = all(_match(cols[c].type, c, g.get(c), w.get(c)) for c in ("amount", "quantity", "unit_price") if c in cols and w.get(c) is not None)
            if ok:
                used.add(i)
                hits += 1
                break
    return hits


def score_set(schema_name: str, rows: list[dict], labels: dict[str, dict]) -> dict:
    schema = get_schema(schema_name)
    per_field: dict[str, dict] = {n: {"tp": 0, "fp": 0, "fn": 0} for n in schema.fields}
    review = {"wrong": 0, "wrong_flagged": 0, "auto": 0, "auto_right": 0, "values": 0}
    page_hits = page_total = 0
    docs_out, seconds, costs = [], [], []
    errors = 0
    for row in rows:
        key = row["doc_key"]
        gold = (labels.get(key) or {}).get("fields") or {}
        accept = (labels.get(key) or {}).get("accept") or {}
        gold_pages = (labels.get(key) or {}).get("pages") or {}
        evidence = (labels.get(key) or {}).get("evidence") or {}
        if row.get("error"):
            errors += 1
            for n, spec in schema.fields.items():
                if gold.get(n) not in (None, []):
                    per_field[n]["fn"] += len(gold[n]) if spec.type == "list" else 1
            docs_out.append({"doc_key": key, "error": row["error"]})
            continue
        res = row["result"]
        seconds.append(res.get("seconds") or 0)
        costs.append((res.get("usage") or {}).get("cost_usd") or 0)
        wrong_fields = []
        for n, spec in schema.fields.items():
            f = res["fields"].get(n) or {}
            got, want, status = f.get("value"), gold.get(n), f.get("status")
            c = per_field[n]
            if spec.type == "list":
                got, want = got or [], want or []
                hit = _match_items(got, want, spec.item)
                c["tp"] += hit
                c["fp"] += len(got) - hit
                c["fn"] += len(want) - hit
                if got:
                    review["values"] += 1
                    right = hit == len(want) == len(got)
                    if status == "auto":
                        review["auto"] += 1
                        review["auto_right"] += right
                    if not right:
                        review["wrong"] += 1
                        review["wrong_flagged"] += status == "needs_review"
                        wrong_fields.append({"field": n, "got": f"{len(got)} lines ({hit} right)", "want": f"{len(want)} lines", "status": status})
                continue
            right = got is not None and want is not None and (
                _match(spec.type, n, got, want) or any(_match(spec.type, n, got, a) for a in (accept.get(n) or []))
            )
            if got is not None:
                review["values"] += 1
                if status == "auto":
                    review["auto"] += 1
                    review["auto_right"] += right
                if not right:
                    review["wrong"] += 1
                    review["wrong_flagged"] += status == "needs_review"
            if right:
                c["tp"] += 1
                want_page = gold_pages.get(n) or (evidence.get(n) or {}).get("page")
                if want_page is not None and f.get("page") is not None:
                    page_total += 1
                    pages = want_page if isinstance(want_page, list) else [want_page]
                    page_hits += int(f.get("page")) in [int(p) for p in pages]
            else:
                if got is not None:
                    c["fp"] += 1
                if want is not None:
                    c["fn"] += 1
                if got is not None or want is not None:
                    wrong_fields.append({"field": n, "got": f.get("printed") if got is not None else None, "got_value": got, "want": want, "page": f.get("page"), "status": status, "reasons": f.get("reasons")})
        docs_out.append({"doc_key": key, "wrong": wrong_fields, "needs_review": res.get("needs_review"), "pages_read": res.get("pages_read"), "seconds": res.get("seconds"), "cost_usd": (res.get("usage") or {}).get("cost_usd")})

    def prf(c: dict) -> dict:
        p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
        r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        f1 = 2 * p * r / (p + r) if p and r else (0.0 if (p is not None and r is not None) else None)
        return {**c, "precision": _r(p), "recall": _r(r), "f1": _r(f1)}

    total = {"tp": sum(c["tp"] for c in per_field.values()), "fp": sum(c["fp"] for c in per_field.values()), "fn": sum(c["fn"] for c in per_field.values())}
    overall = prf(total) | {
        "documents": len(rows),
        "errors": errors,
        "auto_rate": _r(review["auto"] / review["values"]) if review["values"] else None,
        "auto_precision": _r(review["auto_right"] / review["auto"]) if review["auto"] else None,
        "errors_flagged": _r(review["wrong_flagged"] / review["wrong"]) if review["wrong"] else None,
        "wrong_values": review["wrong"],
        "page_correct": _r(page_hits / page_total) if page_total else None,
        "seconds_p50": round(statistics.median(seconds), 2) if seconds else None,
        "cost_per_document_usd": round(statistics.mean(costs), 6) if costs else None,
    }
    return {
        "schema": schema.name,
        "schema_version": schema.version,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overall": overall,
        "fields": {n: prf(c) for n, c in per_field.items()},
        "documents": docs_out,
    }


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def publish(report: dict, stem: Path, *, name: str) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    o = report["overall"]

    def pct(x):
        return "-" if x is None else f"{x * 100:.1f}%"

    lines = [
        f"# {name}",
        "",
        f"Schema `{report['schema']}` v{report['schema_version']}, {o['documents']} labelled documents. Generated {report['generated']}."
        + (f" {report['notes']}" if report.get("notes") else ""),
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Field F1 (micro, all fields and line items) | **{pct(o['f1'])}** |",
        f"| Precision / recall | {pct(o['precision'])} / {pct(o['recall'])} |",
        f"| Values accepted without review | {pct(o['auto_rate'])} |",
        f"| ...of which right | {pct(o['auto_precision'])} |",
        f"| Wrong values sent to review | {pct(o['errors_flagged'])} ({o['wrong_values']} wrong values) |",
        f"| Right values read from the answer's page | {pct(o['page_correct'])} |",
        f"| Time per document, p50 | {o['seconds_p50']} s |",
        f"| Cost per document | ${o['cost_per_document_usd']} |",
        f"| Documents that failed | {o['errors']} |",
        "",
        "| Field | Right | Wrong or extra | Missed | Precision | Recall | F1 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for n, c in report["fields"].items():
        lines.append(f"| {n} | {c['tp']} | {c['fp']} | {c['fn']} | {pct(c['precision'])} | {pct(c['recall'])} | {pct(c['f1'])} |")
    wrong = [(d["doc_key"], w) for d in report["documents"] for w in d.get("wrong", [])]
    if wrong:
        lines += ["", "**What was wrong**", "", "| Document | Field | Extracted | Answer | Review? |", "| --- | --- | --- | --- | --- |"]
        for key, w in wrong:
            lines.append(f"| {key} | {w['field']} | {w.get('got')} | {w.get('want')} | {'yes' if w.get('status') == 'needs_review' else 'no'} |")
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
