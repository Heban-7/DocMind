"""Aggregate raw run outputs into a scored report (JSON and Markdown)."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from evaluation.schema import GoldenSet, ReviewStatus, load_golden
from evaluation.scoring import page_coverage, score_answer, score_figure


def _pct(n: float, d: float) -> float | None:
    return round(100 * n / d, 1) if d else None


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 2)


def _extraction(golden: GoldenSet, run_dir: Path) -> dict:
    docs_out = []
    fig_rows = []
    for doc in golden.documents:
        path = run_dir / "extraction" / f"{doc.doc_key}.json"
        if not path.exists():
            docs_out.append({"doc_key": doc.doc_key, "status": "not run"})
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        pages = {int(k): v for k, v in (raw.get("pages_text") or {}).items()}
        cov = page_coverage(pages, doc.pages, set(raw.get("failed_pages") or []))
        extract = raw.get("stages", {}).get("extract", {})
        total_cost = sum(s.get("total_cost_usd", 0.0) for s in raw.get("stages", {}).values())
        docs_out.append(
            {
                "doc_key": doc.doc_key,
                "doc_class": doc.doc_class.value,
                "pages": doc.pages,
                "engine": raw.get("engine"),
                "tier": raw.get("tier"),
                "device": raw.get("device"),
                "error": raw.get("error"),
                "coverage": cov,
                "extract_seconds": round(extract.get("seconds", 0.0), 1),
                # per page actually extracted: a tier that skips pages must not look fast
                "seconds_per_page": round(extract.get("seconds", 0.0) / max(1, cov["with_content"]), 2),
                "total_seconds": raw.get("total_seconds"),
                "chunks": raw.get("chunks"),
                "facts": len(raw.get("facts") or []),
                "cost_usd": round(total_cost, 4),
            }
        )
        for fig in golden.scored_figures():
            if fig.doc_key != doc.doc_key:
                continue
            r = score_figure(fig, pages, raw.get("facts") or []).to_dict()
            r["doc_class"] = doc.doc_class.value
            r["source"] = fig.source.value
            fig_rows.append(r)

    def fig_summary(rows: list[dict]) -> dict:
        n = len(rows)
        return {
            "figures": n,
            "intact_on_page_pct": _pct(sum(r["on_gold_page"] == "intact" for r in rows), n),
            "split_digits_pct": _pct(sum(r["on_gold_page"] == "split" for r in rows), n),
            "missing_pct": _pct(sum(r["on_any_page"] == "missing" for r in rows), n),
            "wrong_page_pct": _pct(sum(r["found_on_page"] is not None for r in rows), n),
            "row_intact_pct": _pct(sum(r["row_intact"] for r in rows), n),
            "fact_correct_pct": _pct(sum(r["fact_correct"] for r in rows), n),
            "fact_present_but_wrong_pct": _pct(sum(r["fact_present"] and not r["fact_correct"] for r in rows), n),
        }

    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in fig_rows:
        by_class[r["doc_class"]].append(r)
    ran = [d for d in docs_out if d.get("coverage")]
    total_pages = sum(d["pages"] for d in ran)
    engines: dict[str, list[dict]] = defaultdict(list)
    for d in ran:
        engines[d["engine"] or "?"].append(d)
    return {
        "documents": docs_out,
        "figures": fig_summary(fig_rows),
        "figures_by_class": {k: fig_summary(v) for k, v in sorted(by_class.items())},
        "figure_results": fig_rows,
        "pages": {
            "total": total_pages,
            "with_content": sum(d["coverage"]["with_content"] for d in ran),
            "silently_missing": sum(d["coverage"]["silently_missing"] for d in ran),
            "flagged_failed": sum(d["coverage"]["flagged_failed"] for d in ran),
        },
        "speed_by_engine": {
            e: {
                "documents": len(ds),
                "pages": sum(d["pages"] for d in ds),
                "seconds_per_page": round(
                    sum(d["extract_seconds"] for d in ds) / max(1, sum(d["coverage"]["with_content"] for d in ds)), 2
                ),
                "devices": sorted({d["device"] or "?" for d in ds}),
            }
            for e, ds in sorted(engines.items())
        },
        "ingest_cost_usd": round(sum(d["cost_usd"] for d in ran), 4),
        "ingest_seconds": round(sum(d["total_seconds"] or 0 for d in ran), 1),
    }


def _qa(golden: GoldenSet, run_dir: Path) -> dict | None:
    path = run_dir / "qa.jsonl"
    if not path.exists():
        return None
    raw = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            raw[row["question_id"]] = row
    doc_class = {d.doc_key: d.doc_class.value for d in golden.documents}
    results = []
    for q in golden.scored_questions():
        row = raw.get(q.question_id)
        if row is None:
            continue
        if row.get("error"):
            r = score_answer(q, "", cited_pages=[])
            r.correct = False
            r.detail = "error"
            r.error = row["error"]
        else:
            r = score_answer(
                q,
                row.get("answer") or "",
                cited_pages=[p for p in row.get("cited_pages") or [] if p],
                retrieved_pages_top5=row.get("retrieval_top5_pages"),
            )
            usage = row.get("usage") or {}
            r.latency_s = row.get("latency_s")
            r.first_token_s = row.get("first_token_s")
            r.llm_calls = usage.get("llm_calls")
            r.input_tokens = usage.get("input_tokens")
            r.output_tokens = usage.get("output_tokens")
            r.cost_usd = usage.get("total_cost_usd")
        d = r.to_dict()
        d["doc_class"] = doc_class.get(q.doc_key)
        d["question"] = q.question
        d["answer"] = (row.get("answer") or "")[:600]
        d["gold"] = q.gold_answer_text
        results.append(d)

    def summary(rows: list[dict]) -> dict:
        n = len(rows)
        answerable = [r for r in rows if r["qtype"] != "unanswerable"]
        unans = [r for r in rows if r["qtype"] == "unanswerable"]
        prec = [r["citation_precision"] for r in answerable if r["citation_precision"] is not None]
        ret = [r["retrieval_hit_at_5"] for r in answerable if r["retrieval_hit_at_5"] is not None]
        lat = [r["latency_s"] for r in rows if r.get("latency_s")]
        ftt = [r["first_token_s"] for r in rows if r.get("first_token_s")]
        cost = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
        calls = [r["llm_calls"] for r in rows if r.get("llm_calls") is not None]
        return {
            "questions": n,
            "correct_pct": _pct(sum(r["correct"] for r in rows), n),
            "answerable_correct_pct": _pct(sum(r["correct"] for r in answerable), len(answerable)),
            "false_refusal_pct": _pct(sum(r["refused"] and not r["correct"] for r in answerable), len(answerable)),
            "unanswerable_refused_pct": _pct(sum(r["correct"] for r in unans), len(unans)),
            "citation_precision_mean": round(statistics.mean(prec), 3) if prec else None,
            "citation_hit_pct": _pct(sum(bool(r["citation_hit"]) for r in answerable), len(answerable)),
            "retrieval_hit_at_5_pct": _pct(sum(ret), len(ret)),
            "latency_p50_s": _quantile(lat, 0.5),
            "latency_p95_s": _quantile(lat, 0.95),
            "first_token_p50_s": _quantile(ftt, 0.5),
            "llm_calls_mean": round(statistics.mean(calls), 2) if calls else None,
            "cost_per_question_usd": round(statistics.mean(cost), 6) if cost else None,
            "errors": sum(1 for r in rows if r.get("error")),
        }

    by_type: dict[str, list[dict]] = defaultdict(list)
    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_type[r["qtype"]].append(r)
        by_class[r["doc_class"]].append(r)
    return {
        "overall": summary(results),
        "by_type": {k: summary(v) for k, v in sorted(by_type.items())},
        "by_class": {k: summary(v) for k, v in sorted(by_class.items())},
        "results": results,
    }


def build_report(run_dir: Path, *, golden_version: str = "v1", name: str = "") -> dict:
    from evaluation.run import run_metadata

    golden = load_golden(golden_version)
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    review = defaultdict(int)
    for f in golden.figures:
        review[f.review.value] += 1
    return {
        "name": name or run_dir.name,
        "golden_version": golden_version,
        "golden": {
            "documents": len(golden.documents),
            "pages": sum(d.pages for d in golden.documents),
            "figures_scored": len(golden.scored_figures()),
            "questions_scored": len(golden.scored_questions()),
            "figure_review_status": dict(review),
            "confirmed_by_person": sum(f.review in (ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED) for f in golden.figures),
        },
        "run": {**run_metadata(), **meta},
        "extraction": _extraction(golden, run_dir),
        "qa": _qa(golden, run_dir),
    }


def _fmt(v, suffix: str = "") -> str:
    return "n/a" if v is None else f"{v}{suffix}"


def render_markdown(r: dict) -> str:
    ex = r["extraction"]
    f = ex["figures"]
    lines = [
        f"# {r['name']}",
        "",
        f"Golden set {r['golden_version']}: {r['golden']['documents']} documents, {r['golden']['pages']} pages, "
        f"{r['golden']['figures_scored']} figures, {r['golden']['questions_scored']} questions "
        f"({r['golden']['confirmed_by_person']} figures confirmed by a person so far).",
        f"Generated {r['run'].get('generated_at')} on {r['run'].get('machine')}; {r['run'].get('notes', '')}".rstrip("; "),
        "",
        "## Extraction",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Pages with extracted content | {ex['pages']['with_content']} of {ex['pages']['total']} "
        f"({_fmt(_pct(ex['pages']['with_content'], ex['pages']['total']), '%')}) |",
        f"| Pages silently missing (no content, no failure flag) | {ex['pages']['silently_missing']} |",
        f"| Gold figures intact on the right page | {_fmt(f['intact_on_page_pct'], '%')} |",
        f"| Gold figures with digits split by spaces | {_fmt(f['split_digits_pct'], '%')} |",
        f"| Gold figures missing from the whole extraction | {_fmt(f['missing_pct'], '%')} |",
        f"| Gold figures found only on another page | {_fmt(f['wrong_page_pct'], '%')} |",
        f"| Label and value on the same row (table row integrity) | {_fmt(f['row_intact_pct'], '%')} |",
        f"| FactTable holds the right value | {_fmt(f['fact_correct_pct'], '%')} |",
        f"| FactTable holds the figure with a wrong value | {_fmt(f['fact_present_but_wrong_pct'], '%')} |",
        f"| Ingest time, all documents | {ex['ingest_seconds']} s |",
        f"| Ingest API cost, all documents | ${ex['ingest_cost_usd']} |",
        "",
        "**By document class**",
        "",
        "| Class | Figures | Intact on page | Split digits | Missing | Row intact | Fact correct |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cls, s in ex["figures_by_class"].items():
        lines.append(
            f"| {cls} | {s['figures']} | {_fmt(s['intact_on_page_pct'], '%')} | {_fmt(s['split_digits_pct'], '%')} | "
            f"{_fmt(s['missing_pct'], '%')} | {_fmt(s['row_intact_pct'], '%')} | {_fmt(s['fact_correct_pct'], '%')} |"
        )
    lines += ["", "**Speed by engine** (extraction stage, per page that produced content)", "", "| Engine | Documents | Pages | Seconds per page | Device |", "| --- | --- | --- | --- | --- |"]
    for e, s in ex["speed_by_engine"].items():
        lines.append(f"| {e} | {s['documents']} | {s['pages']} | {s['seconds_per_page']} | {', '.join(s['devices'])} |")
    lines += [
        "",
        "**Per document**",
        "",
        "| Document | Class | Pages | Engine | Content pages | Silently missing | Extract s | s per extracted page | Facts | Cost $ |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for d in ex["documents"]:
        if not d.get("coverage"):
            lines.append(f"| {d['doc_key']} | | | {d.get('status')} | | | | | | |")
            continue
        lines.append(
            f"| {d['doc_key']} | {d['doc_class'][:1]} | {d['pages']} | {d['engine']} | {d['coverage']['with_content']} | "
            f"{d['coverage']['silently_missing']} | {d['extract_seconds']} | {d['seconds_per_page']} | {d['facts']} | {d['cost_usd']} |"
        )
    qa = r.get("qa")
    if qa:
        o = qa["overall"]
        lines += [
            "",
            "## Retrieval and answers",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Questions answered correctly | {_fmt(o['correct_pct'], '%')} of {o['questions']} |",
            f"| Answerable questions answered correctly | {_fmt(o['answerable_correct_pct'], '%')} |",
            f"| False refusals on answerable questions | {_fmt(o['false_refusal_pct'], '%')} |",
            f"| Unanswerable questions correctly refused | {_fmt(o['unanswerable_refused_pct'], '%')} |",
            f"| Retrieval: a gold page in the top 5 | {_fmt(o['retrieval_hit_at_5_pct'], '%')} |",
            f"| Citation precision (share of citations on a gold page) | {_fmt(o['citation_precision_mean'])} |",
            f"| Answers citing at least one gold page | {_fmt(o['citation_hit_pct'], '%')} |",
            f"| Latency p50 / p95 | {_fmt(o['latency_p50_s'], ' s')} / {_fmt(o['latency_p95_s'], ' s')} |",
            f"| Time to first token, p50 | {_fmt(o['first_token_p50_s'], ' s')} |",
            f"| LLM calls per question | {_fmt(o['llm_calls_mean'])} |",
            f"| Cost per question | ${_fmt(o['cost_per_question_usd'])} |",
            f"| Errors | {o['errors']} |",
            "",
            "| Question type | Questions | Correct | False refusals | Retrieval hit@5 | Citation precision |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for t, s in qa["by_type"].items():
            lines.append(
                f"| {t} | {s['questions']} | {_fmt(s['correct_pct'], '%')} | {_fmt(s['false_refusal_pct'], '%')} | "
                f"{_fmt(s['retrieval_hit_at_5_pct'], '%')} | {_fmt(s['citation_precision_mean'])} |"
            )
        lines += ["", "| Document class | Questions | Correct | Retrieval hit@5 |", "| --- | --- | --- | --- |"]
        for c, s in qa["by_class"].items():
            lines.append(f"| {c} | {s['questions']} | {_fmt(s['correct_pct'], '%')} | {_fmt(s['retrieval_hit_at_5_pct'], '%')} |")
    lines += [
        "",
        "## How to reproduce",
        "",
        "```",
        "python -m evaluation.run extract --system v1 --run runs/<name>",
        "python -m evaluation.run qa --system v1 --run runs/<name>",
        "python -m evaluation.run score --run runs/<name>",
        "```",
        "",
        "Scores are deterministic (no LLM judge). Golden figures marked `draft` have not yet been confirmed by a person.",
        "",
    ]
    return "\n".join(lines)
