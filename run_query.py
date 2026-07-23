"""
DocMind | Query / Audit CLI (Phase 4).

Usage:
    # Ask (pin one document)
    uv run python run_query.py "What was import tax expenditure?" --doc 212dc42370e2

    # Ask across the whole corpus (IntentRouter decides / federates)
    uv run python run_query.py "What was import tax expenditure?"

    # Audit a claim
    uv run python run_query.py --audit "Revenue was $4.2B in Q3" --doc 212dc42370e2

    # Conversational memory
    uv run python run_query.py "..." --doc 212dc42370e2 --thread demo-1

    # One-time index existing chunks
    uv run python run_query.py --index-only --embed --doc 212dc42370e2 --name sample.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DEFAULT_SAMPLE_PDF
from src.pipeline.phase4 import build_query_indexes, resolve_pdf_path


def _print_answer(answer, *, as_json: bool) -> None:
    if as_json:
        print(answer.model_dump_json(indent=2))
        return
    print("=" * 72)
    print("DocMind | Query")
    print("=" * 72)
    print(f"Doc ID   : {answer.doc_id}")
    print(f"Question : {answer.question}")
    print("-" * 72)
    print(answer.answer)
    print("-" * 72)
    if answer.provenance.is_empty:
        print("Citations: (none)")
    else:
        print(f"Citations: {len(answer.provenance)}")
        for i, c in enumerate(answer.provenance.citations, 1):
            print(
                f"  [{i}] {c.document_name} p{c.page_number} "
                f"| {c.excerpt[:100]!r}"
            )
    if answer.tool_trace:
        print("Tools   : " + ", ".join(t.tool.value for t in answer.tool_trace))
    print("=" * 72)


def _print_verdict(verdict, *, as_json: bool) -> None:
    if as_json:
        print(verdict.model_dump_json(indent=2))
        return
    print("=" * 72)
    print("DocMind | Audit")
    print("=" * 72)
    print(f"Doc ID  : {verdict.doc_id}")
    print(f"Claim   : {verdict.claim}")
    print(f"Status  : {verdict.status.value}")
    print(f"Why     : {verdict.rationale}")
    print("-" * 72)
    if verdict.provenance.is_empty:
        print("Citations: (none)")
    else:
        print(f"Citations: {len(verdict.provenance)}")
        for i, c in enumerate(verdict.provenance.citations, 1):
            print(
                f"  [{i}] {c.document_name} p{c.page_number} "
                f"| {c.excerpt[:100]!r}"
            )
    if verdict.tool_trace:
        print("Tools   : " + ", ".join(t.tool.value for t in verdict.tool_trace))
    print("=" * 72)


def cmd_index(doc_id: str, *, embed: bool, document_name: str) -> int:
    result = build_query_indexes(
        doc_id,
        document_name=document_name or doc_id,
        embed=embed,
        pageindex_llm_client=None,
    )
    print("=" * 72)
    print("DocMind | Index")
    print("=" * 72)
    print(f"Doc ID         : {result.doc_id}")
    print(f"PageIndex      : {result.pageindex_path} "
          f"({result.pageindex_sections} sections)")
    print(f"Facts written  : {result.facts_written}")
    if result.embedded:
        print(f"Chroma upsert  : {result.chunks_embedded} "
              f"(collection total={result.chroma_total})")
    else:
        print("Chroma         : skipped (pass --embed to ingest vectors)")
    print("=" * 72)
    return 0


def cmd_ask(
    question: str,
    *,
    doc_id: str | None,
    pdf: Path | None,
    as_json: bool,
    thread_id: str | None = None,
    enable_memory: bool = False,
) -> int:
    from src.agents.query_agent import build_query_agent

    agent = build_query_agent(
        doc_id,
        pdf_path=pdf,
        enable_memory=enable_memory or bool(thread_id),
    )
    answer = agent.ask(question, thread_id=thread_id)
    _print_answer(answer, as_json=as_json)
    if (enable_memory or thread_id) and not as_json:
        tid = thread_id or "default"
        print(f"Thread   : {tid} (resume with --thread {tid})")
    return 0


def cmd_audit(claim: str, *, doc_id: str, pdf: Path | None, as_json: bool) -> int:
    from src.agents.audit_agent import build_audit_agent

    agent = build_audit_agent(doc_id, pdf_path=pdf)
    verdict = agent.audit(claim)
    _print_verdict(verdict, as_json=as_json)
    return 0 if verdict.status.value == "verified" else 2


def main(argv: list[str] | None = None) -> int:
    from src.observability.langsmith import configure_langsmith

    parser = argparse.ArgumentParser(
        description="Query or audit a DocMind document (Phase 4)."
    )
    parser.add_argument(
        "text",
        nargs="?",
        default=None,
        help="Question text (or claim when --audit is set).",
    )
    parser.add_argument(
        "--doc",
        default=None,
        help="Document id to pin (omit for IntentRouter / corpus-wide search).",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Treat TEXT as a claim to audit instead of a question.",
    )
    parser.add_argument(
        "--index-only",
        action="store_true",
        help="Build PageIndex + FactTable (and optional Chroma) then exit.",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="With --index-only: also embed chunks into Chroma (API cost).",
    )
    parser.add_argument(
        "--pdf",
        default=None,
        help="Source PDF for page bboxes (defaults to triage profile / sample.pdf).",
    )
    parser.add_argument(
        "--name",
        default="",
        help="Document display name for indexing (default: doc id or profile name).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the typed result as JSON.",
    )
    parser.add_argument(
        "--memory",
        action="store_true",
        help="Persist conversation via SqliteSaver (.refinery/checkpoints.sqlite).",
    )
    parser.add_argument(
        "--thread",
        default=None,
        help="Conversation thread_id (implies --memory). Same id resumes history.",
    )
    parser.add_argument(
        "--no-tracing",
        action="store_true",
        help="Disable LangSmith upload for this run.",
    )
    args = parser.parse_args(argv)

    status = configure_langsmith(enabled=False if args.no_tracing else None)
    if status.enabled and not args.json:
        print(f"LangSmith   : ON (project={status.project})")
    elif not args.json and not args.no_tracing and not status.api_key_present:
        # Quiet hint once -- only when they might expect tracing.
        pass

    doc_id = (args.doc or "").strip() or None
    if args.index_only:
        if not doc_id:
            parser.error("--doc is required with --index-only.")
        name = args.name
        if not name:
            pdf_guess = resolve_pdf_path(doc_id, args.pdf)
            name = pdf_guess.name if pdf_guess else doc_id
        return cmd_index(doc_id, embed=args.embed, document_name=name)

    if not args.text or not str(args.text).strip():
        parser.error("TEXT is required unless --index-only is set.")

    pdf = resolve_pdf_path(doc_id, args.pdf) if doc_id else None
    if pdf is None and args.pdf:
        print(f"Warning: --pdf path not found: {args.pdf}", file=sys.stderr)
    if pdf is None and doc_id:
        pdf = DEFAULT_SAMPLE_PDF if DEFAULT_SAMPLE_PDF.exists() else None

    if args.audit:
        if not doc_id:
            parser.error("--doc is required for --audit (for now).")
        return cmd_audit(args.text.strip(), doc_id=doc_id, pdf=pdf, as_json=args.json)
    return cmd_ask(
        args.text.strip(),
        doc_id=doc_id,
        pdf=pdf,
        as_json=args.json,
        thread_id=args.thread,
        enable_memory=args.memory,
    )


if __name__ == "__main__":
    raise SystemExit(main())
