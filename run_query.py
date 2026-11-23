"""
DocMind | Query / Audit CLI, over the documents of the local CLI account.

Usage (ingest first with run_pipeline.py, which prints the document id):
    # Ask (pin one document)
    uv run python run_query.py "What was import tax expenditure?" --doc <document-id>

    # Ask across all documents of the account (IntentRouter decides / federates)
    uv run python run_query.py "What was import tax expenditure?"

    # Audit a claim
    uv run python run_query.py --audit "Revenue was $4.2B in Q3" --doc <document-id>

    # Conversational memory (Postgres checkpointer)
    uv run python run_query.py "..." --doc <document-id> --thread demo-1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


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
                f"  [{i}] {c.document_name} {c.page_ref} "
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
                f"  [{i}] {c.document_name} {c.page_ref} "
                f"| {c.excerpt[:100]!r}"
            )
    if verdict.tool_trace:
        print("Tools   : " + ", ".join(t.tool.value for t in verdict.tool_trace))
    print("=" * 72)


def cmd_ask(
    question: str,
    *,
    doc_id: str | None,
    pdf: Path | None,
    as_json: bool,
    thread_id: str | None = None,
) -> int:
    from src.agents.memory import checkpoint_key, postgres_checkpointer
    from src.agents.query_agent import build_query_agent

    principal, resolver, corpus = _context()
    agent = build_query_agent(
        doc_id,
        stores=_stores(principal),
        pdf_path=pdf,
        pdf_resolver=resolver,
        corpus=corpus,
        checkpointer=postgres_checkpointer() if thread_id else None,
    )
    key = checkpoint_key(principal.tenant_id, thread_id) if thread_id else None
    answer = agent.ask(question, thread_id=key)
    _print_answer(answer, as_json=as_json)
    if thread_id and not as_json:
        print(f"Thread   : {thread_id} (resume with --thread {thread_id})")
    return 0


def _context():
    from src.db import repos
    from src.db.local import local_principal
    from src.models.intent import CorpusDocument
    from src.storage.blobs import get_blob_store

    principal = local_principal()
    blobs = get_blob_store()

    def resolver(doc_id: str) -> Path | None:
        doc = repos.get_document(principal.tenant_id, doc_id)
        try:
            return blobs.local_path(doc.storage_key) if doc else None
        except FileNotFoundError:
            return None

    corpus = [
        CorpusDocument(document_id=d.id, document_name=d.file_name, domain_hint=d.domain_hint, page_count=d.page_count)
        for d in repos.list_documents(principal.tenant_id, ready_only=True)
    ]
    return principal, resolver, corpus


def _stores(principal):
    from src.stores.pg import pg_stores

    return pg_stores(principal.tenant_id)


def cmd_audit(claim: str, *, doc_id: str, pdf: Path | None, as_json: bool) -> int:
    from src.agents.audit_agent import build_audit_agent

    principal, resolver, _ = _context()
    agent = build_audit_agent(doc_id, stores=_stores(principal), pdf_path=pdf or resolver(doc_id))
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
        "--pdf",
        default=None,
        help="Source PDF for page bboxes (defaults to the stored copy of --doc).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the typed result as JSON.",
    )
    parser.add_argument(
        "--thread",
        default=None,
        help="Conversation thread id; the same id resumes the conversation.",
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
    if not args.text or not str(args.text).strip():
        parser.error("TEXT is required.")

    pdf = Path(args.pdf) if args.pdf else None
    if pdf is not None and not pdf.exists():
        print(f"Warning: --pdf path not found: {args.pdf}", file=sys.stderr)
        pdf = None

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
    )


if __name__ == "__main__":
    raise SystemExit(main())
