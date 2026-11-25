"""Compile the published reports into the JSON the web app's benchmark page reads.

    python -m evaluation.export_benchmarks        # writes frontend/src/lib/benchmarks.json

Only files in ``evaluation/reports/`` are read, so the page shows exactly what
the reports in the repository say. Rerun it after publishing a report.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
OUT = ROOT.parent / "frontend" / "src" / "lib" / "benchmarks.json"

# milestone, report file, what changed (one line)
QA_RUNS = [
    ("V1", "v1-baseline", "The original pipeline"),
    ("M2", "m2-v2-extraction", "Page-level reading: text layer, layout model, OCR, vision"),
    ("M3", "m3-postgres", "Postgres with pgvector, one tenant per account"),
    ("M5", "m5-typed-facts", "Typed facts with sign and scale, numbers answered in SQL"),
    ("M6", "m6-retrieval", "Hybrid search over chunks with context"),
    ("M7", "m7-answer-engine", "One streamed model call, every number checked"),
    ("M9", "m9-citation-boxes", "Citation boxes on the cell or text that prints the figure"),
]
FIELD_RUNS = [
    ("Invoices", "m8-invoice-fields"),
    ("Financial statements", "m8-statement-fields"),
]
MODEL_RUNS = [("gpt-4o-mini", "m7-answer-engine"), ("gpt-6-luna", "m7-gpt-6-luna")]


def _load(name: str) -> dict | None:
    path = REPORTS / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _qa(report: dict) -> dict:
    o = ((report.get("qa") or {}).get("overall")) or {}
    keys = (
        "questions", "correct_pct", "false_refusal_pct", "unanswerable_refused_pct", "citation_precision_mean",
        "citation_support_mean", "retrieval_hit_at_5_pct", "latency_p50_s", "first_token_p50_s",
        "cost_per_question_usd", "llm_calls_mean", "box_on_figure_pct", "box_on_figure_facts_only_pct",
    )
    return {k: o.get(k) for k in keys if o.get(k) is not None}


def _extraction(report: dict) -> dict:
    e = report.get("extraction") or {}
    f, p = e.get("figures") or {}, e.get("pages") or {}
    out = {
        "figures_intact_pct": f.get("intact_on_page_pct"),
        "fact_correct_pct": f.get("fact_correct_pct"),
        "pages": p.get("total"),
        "pages_with_content": p.get("with_content"),
        "pages_silently_missing": p.get("silently_missing"),
    }
    return {k: v for k, v in out.items() if v is not None}


def _speed() -> list[dict]:
    r = _load("m4-speed")
    if not r:
        return []
    before = {d["doc_key"]: d for d in (r.get("before") or {}).get("documents", [])}
    out = []
    for d in (r.get("after") or {}).get("documents", []):
        b = before.get(d["doc_key"], {})
        out.append(
            {
                "document": d["doc_key"],
                "pages": d.get("pages"),
                "before_min": round(b["total_s"] / 60, 1) if b.get("total_s") else None,
                "after_min": round(d["total_s"] / 60, 1) if d.get("total_s") else None,
                "first_searchable_s": d.get("first_searchable_s"),
            }
        )
    return out


def build() -> dict:
    milestones = []
    for key, name, change in QA_RUNS:
        r = _load(name)
        if r is None:
            continue
        milestones.append({"milestone": key, "report": f"evaluation/reports/{name}.md", "change": change, **_qa(r), **_extraction(r)})
    fields = []
    for label, name in FIELD_RUNS:
        r = _load(name)
        if r is None:
            continue
        o = r.get("overall") or {}
        fields.append(
            {
                "set": label,
                "documents": o.get("documents") or r.get("documents"),
                "f1_pct": round(100 * o["f1"], 1) if o.get("f1") is not None else None,
                "auto_rate_pct": round(100 * o["auto_rate"], 1) if o.get("auto_rate") is not None else None,
                "auto_precision_pct": round(100 * o["auto_precision"], 1) if o.get("auto_precision") is not None else None,
                "errors_flagged": o.get("errors_flagged"),
                "wrong_values": o.get("wrong_values"),
                "cost_per_document_usd": o.get("cost_per_document_usd"),
                "seconds_p50": o.get("seconds_p50"),
                "report": f"evaluation/reports/{name}.md",
            }
        )
    models = []
    for model, name in MODEL_RUNS:
        r = _load(name)
        if r is not None:
            models.append({"model": model, "report": f"evaluation/reports/{name}.md", **_qa(r)})
    first = _load(QA_RUNS[0][1]) or {}
    golden = first.get("golden") or {}
    return {
        "golden_set": {
            "documents": golden.get("documents"),
            "pages": golden.get("pages"),
            "questions": (_qa(first) or {}).get("questions"),
            "note": "Drafted from the corpus; marked draft until a person confirms each item.",
        },
        "milestones": milestones,
        "fields": fields,
        "models": models,
        "speed": _speed(),
    }


def main() -> None:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(data['milestones'])} milestones, {len(data['fields'])} field sets)")


if __name__ == "__main__":
    main()
