"""Field benchmark (M8): extract schema fields from labelled documents and score them.

    python -m evaluation.fields ingest  --run runs/m8 --set invoice
    python -m evaluation.fields extract --run runs/m8 --set invoice [--model gpt-4o-mini]
    python -m evaluation.fields score   --run runs/m8 --set invoice [--publish m8-invoice]

A set is a folder under evaluation/golden/schemas/<schema>/ with
documents.json (which PDFs) and labels.jsonl (the answers). The run folder
works like the QA benchmark's: extraction/<doc_key>.json records the
ingested document (doc_id), refinery/ holds the stored files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EVAL_ROOT.parent
SETS = EVAL_ROOT / "golden" / "schemas"


def _resolve(run: str) -> Path:
    p = Path(run)
    return p if p.is_absolute() else EVAL_ROOT / p


def _prepare_env(run_dir: Path) -> None:
    os.environ["DOCMIND_REFINERY_DIR"] = str(run_dir / "refinery")
    os.environ.pop("DOCMIND_STORAGE_DIR", None)
    os.environ.setdefault("DOCMIND_EVAL_ACCOUNT", f"eval-{run_dir.name}")
    os.environ["LANGSMITH_TRACING"] = "false"


def load_set(name: str) -> tuple[dict, dict[str, dict]]:
    """(documents.json, labels by doc_key) of a labelled set."""
    folder = SETS / name
    docs = json.loads((folder / "documents.json").read_text(encoding="utf-8"))
    labels: dict[str, dict] = {}
    path = folder / "labels.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                labels[row["doc_key"]] = row
    return docs, labels


def cmd_ingest(args) -> None:
    run_dir = _resolve(args.run)
    _prepare_env(run_dir)
    from evaluation.systems import current

    docs, _ = load_set(args.set)
    corpus = PROJECT_ROOT / docs["corpus_dir"]
    out_dir = run_dir / "extraction"
    out_dir.mkdir(parents=True, exist_ok=True)
    for d in docs["documents"]:
        target = out_dir / f"{d['doc_key']}.json"
        if target.exists() and not args.force:
            print(f"skip {d['doc_key']} (done)", flush=True)
            continue
        print(f"ingest {d['doc_key']} ...", flush=True)
        result = current.run_document(corpus / d["file_name"])
        result["doc_key"] = d["doc_key"]
        target.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(f"  -> {result.get('error') or str(result.get('engine')) + ' ' + str(result.get('total_seconds')) + 's'}", flush=True)


def cmd_extract(args) -> None:
    """Run the product's extractor on every labelled document of the set."""
    run_dir = _resolve(args.run)
    _prepare_env(run_dir)
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    from evaluation.systems import current
    from src.db import repos
    from src.document.model import DocumentModel
    from src.llm.factory import client_for_request, get_text_client
    from src.schemas.extract import extract_fields, page_images
    from src.schemas.schema import get_schema
    from src.storage.blobs import get_blob_store

    docs, labels = load_set(args.set)
    schema = get_schema(args.set)
    llm = client_for_request(args.model) if args.model else get_text_client()
    principal = current._principal()
    out_path = run_dir / f"fields-{args.set}{'-' + args.tag if args.tag else ''}.jsonl"
    done = set()
    if out_path.exists() and not args.force:
        done = {json.loads(line)["doc_key"] for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    with open(out_path, "a" if done else "w", encoding="utf-8") as fh:
        for d in docs["documents"]:
            key = d["doc_key"]
            if key in done or key not in labels:
                continue
            ext = run_dir / "extraction" / f"{key}.json"
            if not ext.exists():
                print(f"{key}: not ingested (run ingest first)")
                continue
            row: dict = {"doc_key": key}
            try:
                doc_id = json.loads(ext.read_text(encoding="utf-8"))["doc_id"]
                doc = repos.require_document(principal.tenant_id, doc_id)
                model = DocumentModel.model_validate_json(get_blob_store().local_path(doc.model_key).read_text(encoding="utf-8"))
                images = None if args.no_images else page_images(PROJECT_ROOT / docs["corpus_dir"] / d["file_name"])
                row["result"] = extract_fields(model, schema, llm, document_id=doc_id, page_image=images).to_dict()
            except Exception as exc:  # record and continue
                row["error"] = f"{type(exc).__name__}: {exc}"
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            res = row.get("result") or {}
            print(f"{key}: {row.get('error') or str(len(res.get('needs_review', []))) + ' to review, ' + str(res.get('seconds')) + 's'}", flush=True)


def cmd_score(args) -> None:
    from evaluation.field_scoring import publish, score_set

    run_dir = _resolve(args.run)
    out_path = run_dir / f"fields-{args.set}{'-' + args.tag if args.tag else ''}.jsonl"
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    docs, labels = load_set(args.set)
    report = score_set(args.set, rows, labels)
    report["run"] = str(run_dir.relative_to(EVAL_ROOT)) if run_dir.is_relative_to(EVAL_ROOT) else str(run_dir)
    report["tag"] = args.tag or ""
    meta = run_dir / f"fields-{args.set}{'-' + args.tag if args.tag else ''}.meta.json"
    if meta.exists():
        report["notes"] = json.loads(meta.read_text(encoding="utf-8")).get("notes", "")
    (run_dir / f"fields-{args.set}{'-' + args.tag if args.tag else ''}.report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    o = report["overall"]
    print(json.dumps({k: o[k] for k in ("documents", "precision", "recall", "f1", "auto_rate", "auto_precision", "errors_flagged", "cost_per_document_usd", "seconds_p50")}, indent=1))
    if args.publish:
        publish(report, EVAL_ROOT / "reports" / args.publish, name=args.name or args.publish)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m evaluation.fields")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ingest", "extract", "score"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        p.add_argument("--set", required=True)
        p.add_argument("--force", action="store_true")
        p.add_argument("--tag", default="", help="a name for this variant of the run (model, settings)")
        if name == "extract":
            p.add_argument("--model", default=None)
            p.add_argument("--no-images", action="store_true", help="no second look at scanned pages' images")
        if name == "score":
            p.add_argument("--publish", default="", help="also write evaluation/reports/<name>.md/.json")
            p.add_argument("--name", default="")
    args = ap.parse_args(argv)
    {"ingest": cmd_ingest, "extract": cmd_extract, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    main(sys.argv[1:])
