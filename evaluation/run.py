"""Run a DocMind version against the golden set and score it.

    python -m evaluation.run extract --run runs/m3
    python -m evaluation.run qa      --run runs/m3
    python -m evaluation.run score   --run runs/m3 --name "M3"

``extract`` and ``qa`` write raw outputs under the run folder (git-ignored);
``score`` turns them into ``report.json`` and ``report.md``. Every run folder
keeps its own files (stored PDFs, document models) and its own account in
Postgres, so a run never touches the developer's local data.

The only system in the tree is ``current`` (the product as it ships). The V1
baseline and the M2 run used systems ``v1`` and ``v2`` at commit 9d8509f.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EVAL_ROOT.parent


def _prepare_env(run_dir: Path) -> None:
    """Point the system under test at the run folder before it is imported."""
    os.environ["DOCMIND_REFINERY_DIR"] = str(run_dir / "refinery")
    os.environ.pop("DOCMIND_STORAGE_DIR", None)  # stored files go under the run folder
    os.environ.setdefault("DOCMIND_EVAL_ACCOUNT", f"eval-{run_dir.name}")
    os.environ["LANGSMITH_TRACING"] = "false"  # no third-party tracing of benchmark data


def _corpus_dir() -> Path:
    return Path(os.getenv("DOCMIND_CORPUS_DIR", PROJECT_ROOT / "data" / "data"))


def _resolve(run: str) -> Path:
    p = Path(run)
    return p if p.is_absolute() else EVAL_ROOT / p


def cmd_extract(args) -> None:
    run_dir = _resolve(args.run)
    _prepare_env(run_dir)
    from evaluation.draft.build_golden_v1 import sha256_of
    from evaluation.schema import load_golden

    golden = load_golden(args.golden)
    system = _system(args.system)
    out_dir = run_dir / "extraction"
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(args.docs.split(",")) if args.docs else None
    for doc in golden.documents:
        if wanted and doc.doc_key not in wanted:
            continue
        target = out_dir / f"{doc.doc_key}.json"
        if target.exists() and not args.force:
            print(f"skip {doc.doc_key} (done)")
            continue
        pdf = _corpus_dir() / doc.file_name
        if sha256_of(pdf) != doc.sha256:
            raise SystemExit(f"{doc.file_name}: file differs from the golden set (sha256 mismatch)")
        print(f"extract {doc.doc_key} ({doc.pages} pages) ...", flush=True)
        result = system.run_document(pdf)
        result["doc_key"] = doc.doc_key
        target.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        status = result.get("error") or f"{result.get('engine')} {result.get('total_seconds')}s"
        print(f"  -> {status}", flush=True)


def cmd_qa(args) -> None:
    run_dir = _resolve(args.run)
    _prepare_env(run_dir)
    from evaluation.schema import load_golden

    golden = load_golden(args.golden)
    system = _system(args.system)
    extraction = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (run_dir / "extraction").glob("*.json")}
    out_path = run_dir / "qa.jsonl"
    done = set()
    if out_path.exists() and not args.force:
        done = {json.loads(line)["question_id"] for line in out_path.read_text(encoding="utf-8").splitlines() if line}
    wanted = set(args.docs.split(",")) if args.docs else None
    with open(out_path, "a" if done else "w", encoding="utf-8") as fh:
        for q in golden.scored_questions():
            if q.question_id in done or (wanted and q.doc_key not in wanted):
                continue
            ext = extraction.get(q.doc_key)
            if not ext or ext.get("error"):
                row = {"question_id": q.question_id, "error": "document was not ingested"}
            else:
                pdf = _corpus_dir() / golden.document(q.doc_key).file_name
                try:
                    row = system.ask(ext["doc_id"], pdf, q.question, model=args.model)
                    row["question_id"] = q.question_id
                except Exception as exc:
                    row = {"question_id": q.question_id, "error": f"{type(exc).__name__}: {exc}"}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"{q.question_id}: {(row.get('answer') or row.get('error') or '')[:90]}", flush=True)


def cmd_score(args) -> None:
    run_dir = _resolve(args.run)
    from evaluation.report import build_report

    report = build_report(run_dir, golden_version=args.golden, name=args.name)
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    from evaluation.report import render_markdown

    md = render_markdown(report)
    (run_dir / "report.md").write_text(md, encoding="utf-8")
    if args.publish:
        dest = EVAL_ROOT / "reports"
        dest.mkdir(exist_ok=True)
        (dest / f"{args.publish}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        (dest / f"{args.publish}.md").write_text(md, encoding="utf-8")
    print(md)


def _system(name: str):
    if name == "current":
        from evaluation.systems import current

        return current
    if name in {"v1", "v2"}:
        raise SystemExit(f"system {name!r} was removed in M3; check out commit 9d8509f to run it")
    raise SystemExit(f"unknown system {name!r}")


def run_metadata() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "machine": platform.processor() or platform.machine(),
        "platform": platform.platform(),
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m evaluation.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "qa"):
        p = sub.add_parser(name)
        p.add_argument("--system", default="current")
        p.add_argument("--run", required=True)
        p.add_argument("--golden", default="v1")
        p.add_argument("--docs", default="", help="comma-separated doc_keys (default: all)")
        p.add_argument("--force", action="store_true")
        if name == "qa":
            p.add_argument("--model", default=None, help="model name; default = the system's own default")
    p = sub.add_parser("score")
    p.add_argument("--run", required=True)
    p.add_argument("--golden", default="v1")
    p.add_argument("--name", default="")
    p.add_argument("--publish", default="", help="also copy the report to evaluation/reports/<name>.*")
    args = ap.parse_args(argv)
    {"extract": cmd_extract, "qa": cmd_qa, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    main(sys.argv[1:])
