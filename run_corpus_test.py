"""
DocMind | Corpus Validation & End-to-End Stress Test

YOU choose documents and questions from the CLI.

Examples:

    # Query an already-indexed doc (no embed / no re-extract)
    uv run python run_corpus_test.py --queries-only --doc-id 212dc42370e2 \\
        --q1 "What is this report about?" \\
        --q2 "What was import tax expenditure in FY 2020/21?" \\
        --claim "Revenue on Mars was $4.2B in Q3"

    # One custom question only (skip the default 3-check suite)
    uv run python run_corpus_test.py --queries-only --file sample.pdf \\
        --query "What was import tax expenditure in FY 2020/21?"

    # One custom audit only
    uv run python run_corpus_test.py --queries-only --file sample.pdf \\
        --audit "Revenue on Mars was $4.2B in Q3"

    # Ingest selected PDFs then run default (or overridden) checks
    uv run python run_corpus_test.py --file sample.pdf --file "tax_expenditure_ethiopia_2021_22.pdf"

    # Ingest without embeddings, then query later
    uv run python run_corpus_test.py --file sample.pdf --skip-embed --ingest-only
    uv run python run_corpus_test.py --queries-only --file sample.pdf --query "..."

Reports:
  - Terminal: status grid + per-query Question / Evidence / Answer blocks
  - ``data/evaluation_report.json``
"""

from __future__ import annotations

import argparse
import logging
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agents.audit_agent import build_audit_agent
from src.agents.query_agent import build_query_agent
from src.agents.triage import TriageAgent
from src.chunking.engine import ContextAwareChunker
from src.config import CHUNKS_DIR, DATA_DIR, EXTRACTIONS_DIR, PROJECT_ROOT, PROFILES_DIR
from src.extraction.router import ExtractionRouter
from src.facts.store import FactStore
from src.models.document_profile import DocumentProfile
from src.models.query import AuditStatus, QueryAnswer
from src.observability.langsmith import configure_langsmith
from src.pipeline.phase4 import build_query_indexes, resolve_pdf_path

logger = logging.getLogger("docmind.corpus_test")

REPORT_PATH = PROJECT_ROOT / "data" / "evaluation_report.json"

StatusLabel = Literal["PASS", "FAIL", "SKIP", "ERROR"]
QueryKind = Literal["conceptual", "numerical", "audit_unanswerable", "custom_query", "custom_audit"]


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------


class QueryEvalResult(BaseModel):
    query: str
    kind: QueryKind
    status: StatusLabel
    detail: str = ""
    answer_or_rationale: str = ""
    extracted_evidence: list[str] = Field(
        default_factory=list,
        description="Citation excerpts / evidence snippets shown to the user",
    )
    citations: int = 0
    tools: list[str] = Field(default_factory=list)
    audit_status: str | None = None


class DocumentEvalResult(BaseModel):
    file_name: str
    doc_id: str | None = None
    triage_tier: str = ""
    page_count: int = 0
    chunks_generated: int = 0
    facts_written: int = 0
    chunks_embedded: int = 0
    ingest_error: str | None = None
    query1_status: StatusLabel = "SKIP"
    query2_status: StatusLabel = "SKIP"
    audit_gate: StatusLabel = "SKIP"
    queries: list[QueryEvalResult] = Field(default_factory=list)


class CorpusEvaluationReport(BaseModel):
    generated_at: str
    data_dir: str
    pdf_count: int
    docs_attempted: int
    docs_succeeded: int
    options: dict[str, Any] = Field(default_factory=dict)
    documents: list[DocumentEvalResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Document selection
# ---------------------------------------------------------------------------


def discover_pdfs(data_dir: Path, *, pattern: str = "*.pdf") -> list[Path]:
    return sorted(p for p in data_dir.glob(pattern) if p.is_file())


def resolve_pdf_by_name(data_dir: Path, name: str) -> Path | None:
    """Resolve a user-supplied file name or path to an existing PDF."""
    raw = Path(name)
    candidates = [
        raw if raw.is_absolute() else None,
        data_dir / name,
        data_dir / raw.name,
        PROJECT_ROOT / name,
    ]
    for path in candidates:
        if path is not None and path.is_file():
            return path
    # Case-insensitive match in data_dir
    lowered = raw.name.lower()
    for path in data_dir.glob("*.pdf"):
        if path.name.lower() == lowered:
            return path
    return None


def load_profile_by_doc_id(doc_id: str) -> DocumentProfile | None:
    path = PROFILES_DIR / f"{doc_id}.json"
    if not path.exists():
        return None
    try:
        return DocumentProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_existing_profile(pdf_path: Path) -> DocumentProfile | None:
    if not PROFILES_DIR.exists():
        return None
    name = pdf_path.name
    for path in PROFILES_DIR.glob("*.json"):
        try:
            profile = DocumentProfile.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception:
            continue
        if profile.source_filename == name or Path(profile.source_path).name == name:
            return profile
    return None


def select_targets(
    data_dir: Path,
    *,
    files: list[str],
    doc_ids: list[str],
    pattern: str,
    max_docs: int | None,
) -> list[tuple[str, Path | None, DocumentProfile | None]]:
    """Return list of (label, pdf_path|None, profile|None) chosen by the user.

    Priority:
      1. Explicit --doc-id
      2. Explicit --file
      3. --glob discovery (legacy bulk mode)
    """
    targets: list[tuple[str, Path | None, DocumentProfile | None]] = []
    seen: set[str] = set()

    for doc_id in doc_ids:
        doc_id = doc_id.strip()
        if not doc_id or doc_id in seen:
            continue
        profile = load_profile_by_doc_id(doc_id)
        pdf = None
        if profile:
            pdf = resolve_pdf_path(doc_id) or resolve_pdf_by_name(
                data_dir, profile.source_filename
            )
            label = profile.source_filename or doc_id
        else:
            label = doc_id
        targets.append((label, pdf, profile))
        seen.add(doc_id)

    for name in files:
        pdf = resolve_pdf_by_name(data_dir, name)
        if pdf is None:
            raise FileNotFoundError(f"PDF not found for --file {name!r} under {data_dir}")
        profile = load_existing_profile(pdf)
        key = profile.doc_id if profile else pdf.name
        if key in seen:
            continue
        targets.append((pdf.name, pdf, profile))
        seen.add(key)

    if not targets:
        for pdf in discover_pdfs(data_dir, pattern=pattern):
            profile = load_existing_profile(pdf)
            key = profile.doc_id if profile else pdf.name
            if key in seen:
                continue
            targets.append((pdf.name, pdf, profile))
            seen.add(key)

    if max_docs is not None:
        targets = targets[: max(0, max_docs)]
    return targets


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


def ingest_pdf(
    pdf_path: Path,
    *,
    skip_embed: bool = False,
) -> tuple[DocumentProfile, int, int, int]:
    triage = TriageAgent()
    profile, _ = triage.profile_and_save(str(pdf_path))

    router = ExtractionRouter()
    engine = router.get_engine(profile)
    markdown = engine.extract(profile.source_path)

    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
    (EXTRACTIONS_DIR / f"{profile.doc_id}.md").write_text(markdown, encoding="utf-8")

    chunker = ContextAwareChunker()
    chunks = chunker.chunk(markdown)

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    chunks_path = CHUNKS_DIR / f"{profile.doc_id}.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(chunk.model_dump_json() + "\n")

    index = build_query_indexes(
        profile.doc_id,
        document_name=profile.source_filename,
        embed=not skip_embed,
        pageindex_llm_client=None,
    )
    return profile, len(chunks), index.facts_written, index.chunks_embedded


def count_chunks(doc_id: str) -> int:
    path = CHUNKS_DIR / f"{doc_id}.jsonl"
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Default query builders
# ---------------------------------------------------------------------------


_BAD_METRIC_RE = re.compile(
    r"(contents\s*:|table of contents|^\d+\.\s*$|^\.+$|executive summary\.+)",
    re.I,
)


def build_conceptual_query(profile: DocumentProfile) -> str:
    domain = (profile.domain_hint or "general").replace("_", " ")
    return (
        f"In plain language, what is the main subject and purpose of the "
        f"document '{profile.source_filename}' (domain hint: {domain})?"
    )


def build_numerical_query(doc_id: str, profile: DocumentProfile) -> str:
    store = FactStore()
    facts = store.search(doc_id=doc_id, limit=40)
    for fact in facts:
        metric = (fact.metric or "").strip()
        if not metric or len(metric) < 4:
            continue
        if _BAD_METRIC_RE.search(metric):
            continue
        if len(metric) > 80:
            continue
        if fact.period:
            return f"What was {metric} for {fact.period}?"
        if fact.value_text:
            return f"What was the reported value for {metric}?"
    return (
        f"What key numerical figures (revenue, expenditure, totals, or rates) "
        f"are reported in '{profile.source_filename}'?"
    )


def build_unanswerable_claim(profile: DocumentProfile) -> str:
    return (
        f"The document '{profile.source_filename}' states that Martian colony "
        f"revenue was exactly $4.2 billion in Q3 2099."
    )


def _is_refusal(text: str) -> bool:
    lowered = (text or "").strip().lower()
    markers = (
        "could not find",
        "not found",
        "unverifiable",
        "no supporting",
        "i don't know",
        "i do not know",
    )
    return (not lowered) or any(m in lowered for m in markers)


def _evidence_from_answer(answer: QueryAnswer) -> list[str]:
    out: list[str] = []
    for c in answer.provenance.citations:
        excerpt = (c.excerpt or "").strip().replace("\n", " ")
        if not excerpt:
            continue
        if len(excerpt) > 280:
            excerpt = excerpt[:280] + "..."
        out.append(f"{c.document_name} {c.page_ref}: {excerpt}")
    return out


def _evidence_from_audit(verdict) -> list[str]:
    out: list[str] = []
    for c in verdict.provenance.citations:
        excerpt = (c.excerpt or "").strip().replace("\n", " ")
        if not excerpt:
            continue
        if len(excerpt) > 280:
            excerpt = excerpt[:280] + "..."
        out.append(f"{c.document_name} {c.page_ref}: {excerpt}")
    return out


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


def eval_query_agent(
    *,
    doc_id: str,
    question: str,
    kind: QueryKind,
    pdf_path: Path | None,
) -> QueryEvalResult:
    try:
        agent = build_query_agent(doc_id, pdf_path=pdf_path)
        answer = agent.ask(question)
        tools = [t.tool.value for t in answer.tool_trace]
        evidence = _evidence_from_answer(answer)
        citations = len(answer.provenance)
        refusal = _is_refusal(answer.answer)
        if not refusal and citations >= 1:
            status: StatusLabel = "PASS"
            detail = "Cited answer produced."
        elif not refusal and citations == 0:
            status = "FAIL"
            detail = "Answer lacked required provenance citations."
        else:
            status = "FAIL"
            detail = "Agent refused / found no grounded answer."
        if kind == "numerical" and status == "PASS" and "structured_query" not in tools:
            detail += " (note: structured_query not in tool_trace)"
        return QueryEvalResult(
            query=question,
            kind=kind,
            status=status,
            detail=detail,
            answer_or_rationale=answer.answer,
            extracted_evidence=evidence,
            citations=citations,
            tools=tools,
        )
    except Exception as exc:
        logger.exception("Query eval failed (%s)", kind)
        return QueryEvalResult(
            query=question,
            kind=kind,
            status="ERROR",
            detail=str(exc),
            answer_or_rationale=traceback.format_exc()[-800:],
        )


def eval_audit(
    *,
    doc_id: str,
    claim: str,
    kind: QueryKind,
    pdf_path: Path | None,
    expect_unverifiable: bool,
) -> QueryEvalResult:
    try:
        agent = build_audit_agent(doc_id, pdf_path=pdf_path)
        verdict = agent.audit(claim)
        tools = [t.tool.value for t in verdict.tool_trace]
        evidence = _evidence_from_audit(verdict)
        if expect_unverifiable:
            if verdict.status is AuditStatus.UNVERIFIABLE:
                status: StatusLabel = "PASS"
                detail = "Correctly flagged unverifiable."
            else:
                status = "FAIL"
                detail = (
                    f"Expected unverifiable, got {verdict.status.value} "
                    f"with {len(verdict.provenance)} citation(s)."
                )
        else:
            # Custom audit: report outcome without forcing unverifiable.
            status = "PASS" if verdict.status is AuditStatus.VERIFIED else "FAIL"
            detail = f"Audit result: {verdict.status.value}"
            if verdict.status is AuditStatus.VERIFIED and verdict.provenance.is_empty:
                status = "FAIL"
                detail = "verified without citations (invalid)."
        return QueryEvalResult(
            query=claim,
            kind=kind,
            status=status,
            detail=detail,
            answer_or_rationale=(
                f"[{verdict.status.value}] {verdict.rationale}"
            ).strip(),
            extracted_evidence=evidence,
            citations=len(verdict.provenance),
            tools=tools,
            audit_status=verdict.status.value,
        )
    except Exception as exc:
        logger.exception("Audit eval failed")
        return QueryEvalResult(
            query=claim,
            kind=kind,
            status="ERROR",
            detail=str(exc),
            answer_or_rationale=traceback.format_exc()[-800:],
        )


# ---------------------------------------------------------------------------
# Per-document orchestration
# ---------------------------------------------------------------------------


class EvalPlan(BaseModel):
    """Which checks to run (CLI-driven)."""

    run_suite: bool = True
    q1: str | None = None
    q2: str | None = None
    claim: str | None = None
    custom_query: str | None = None
    custom_audit: str | None = None


def evaluate_document(
    *,
    label: str,
    pdf_path: Path | None,
    existing_profile: DocumentProfile | None,
    queries_only: bool,
    skip_embed: bool,
    skip_queries: bool,
    plan: EvalPlan,
) -> DocumentEvalResult:
    row = DocumentEvalResult(file_name=label)
    profile = existing_profile

    try:
        if queries_only:
            if profile is None and pdf_path is not None:
                profile = load_existing_profile(pdf_path)
            if profile is None:
                row.ingest_error = (
                    "No saved profile for this target; ingest first "
                    "(omit --queries-only) or pass a valid --doc-id."
                )
                row.query1_status = row.query2_status = row.audit_gate = "SKIP"
                return row
            row.doc_id = profile.doc_id
            row.triage_tier = profile.strategy_tier.value
            row.page_count = profile.page_count
            row.chunks_generated = count_chunks(profile.doc_id)
            row.facts_written = FactStore().count(profile.doc_id)
        else:
            if pdf_path is None:
                row.ingest_error = "Ingest requires a PDF path (--file)."
                return row
            profile, n_chunks, n_facts, n_embedded = ingest_pdf(
                pdf_path, skip_embed=skip_embed
            )
            row.doc_id = profile.doc_id
            row.triage_tier = profile.strategy_tier.value
            row.page_count = profile.page_count
            row.chunks_generated = n_chunks
            row.facts_written = n_facts
            row.chunks_embedded = n_embedded
            row.file_name = profile.source_filename or label
    except Exception as exc:
        logger.exception("Ingest failed for %s", label)
        row.ingest_error = str(exc)
        row.query1_status = row.query2_status = row.audit_gate = "ERROR"
        return row

    if skip_queries:
        row.query1_status = row.query2_status = row.audit_gate = "SKIP"
        return row

    assert row.doc_id is not None and profile is not None
    pdf_for_bbox = (
        resolve_pdf_path(row.doc_id, pdf_path)
        or pdf_path
        or resolve_pdf_path(row.doc_id)
    )

    results: list[QueryEvalResult] = []

    # Custom single-shot modes
    if plan.custom_query:
        results.append(
            eval_query_agent(
                doc_id=row.doc_id,
                question=plan.custom_query,
                kind="custom_query",
                pdf_path=pdf_for_bbox,
            )
        )
    if plan.custom_audit:
        results.append(
            eval_audit(
                doc_id=row.doc_id,
                claim=plan.custom_audit,
                kind="custom_audit",
                pdf_path=pdf_for_bbox,
                expect_unverifiable=False,
            )
        )

    # Default 3-check suite (unless user only asked for custom query/audit)
    if plan.run_suite:
        q1_text = plan.q1 or build_conceptual_query(profile)
        q2_text = plan.q2 or build_numerical_query(row.doc_id, profile)
        claim_text = plan.claim or build_unanswerable_claim(profile)

        q1 = eval_query_agent(
            doc_id=row.doc_id,
            question=q1_text,
            kind="conceptual",
            pdf_path=pdf_for_bbox,
        )
        q2 = eval_query_agent(
            doc_id=row.doc_id,
            question=q2_text,
            kind="numerical",
            pdf_path=pdf_for_bbox,
        )
        q3 = eval_audit(
            doc_id=row.doc_id,
            claim=claim_text,
            kind="audit_unanswerable",
            pdf_path=pdf_for_bbox,
            expect_unverifiable=True,
        )
        results.extend([q1, q2, q3])
        row.query1_status = q1.status
        row.query2_status = q2.status
        row.audit_gate = q3.status
    else:
        # Map first custom results into summary columns when suite skipped
        for r in results:
            if r.kind in {"conceptual", "custom_query"} and row.query1_status == "SKIP":
                row.query1_status = r.status
            elif r.kind == "numerical" and row.query2_status == "SKIP":
                row.query2_status = r.status
            elif r.kind in {"audit_unanswerable", "custom_audit"} and row.audit_gate == "SKIP":
                row.audit_gate = r.status

    row.queries = results
    return row


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _clip(text: str, n: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= n:
        return text
    return text[: n - 3] + "..."


def print_summary_table(docs: list[DocumentEvalResult]) -> None:
    """Compact status grid + detailed Question / Evidence / Answer blocks."""
    headers = (
        "File",
        "Tier",
        "Pages",
        "Chunks",
        "Q1",
        "Q2",
        "Audit",
    )
    grid: list[tuple[str, ...]] = []
    for d in docs:
        grid.append(
            (
                _clip(d.file_name, 36),
                _clip(d.triage_tier or "-", 16),
                str(d.page_count),
                str(d.chunks_generated),
                d.query1_status,
                d.query2_status,
                d.audit_gate,
            )
        )

    widths = [len(h) for h in headers]
    for row in grid:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cols: tuple[str, ...]) -> str:
        return " | ".join(c.ljust(widths[i]) for i, c in enumerate(cols))

    line = "-+-".join("-" * w for w in widths)
    print()
    print("=" * 96)
    print("DocMind | Corpus Evaluation -- Status Grid")
    print("=" * 96)
    print(fmt(headers))
    print(line)
    for row in grid:
        print(fmt(row))
    print("=" * 96)

    print()
    print("=" * 96)
    print("DocMind | Question / Extracted Evidence / Answer")
    print("=" * 96)
    for d in docs:
        print()
        print(f"### {d.file_name}  (doc_id={d.doc_id or '-'})")
        if d.ingest_error:
            print(f"  INGEST ERROR: {d.ingest_error}")
            continue
        if not d.queries:
            print("  (no queries run)")
            continue
        for i, q in enumerate(d.queries, 1):
            print("-" * 96)
            print(f"[{i}] kind={q.kind}  status={q.status}  citations={q.citations}")
            if q.tools:
                print(f"    tools   : {', '.join(q.tools)}")
            print(f"    question: {q.query}")
            if q.extracted_evidence:
                print("    evidence:")
                for ev in q.extracted_evidence:
                    print(f"      - {ev}")
            else:
                print("    evidence: (none)")
            print(f"    answer  : {q.answer_or_rationale}")
            if q.detail:
                print(f"    detail  : {q.detail}")
    print("=" * 96)

    n = len(docs)
    print(
        f"Totals: docs={n} | Q1 PASS="
        f"{sum(1 for d in docs if d.query1_status == 'PASS')}/{n} | "
        f"Q2 PASS={sum(1 for d in docs if d.query2_status == 'PASS')}/{n} | "
        f"Audit PASS={sum(1 for d in docs if d.audit_gate == 'PASS')}/{n}"
    )
    print()


def save_report(report: CorpusEvaluationReport, path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Corpus validation -- you choose docs and queries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help=f"Directory of PDFs (default: {DATA_DIR})",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        dest="files",
        help="PDF file name or path to include (repeatable). Example: --file sample.pdf",
    )
    parser.add_argument(
        "--doc-id",
        action="append",
        default=[],
        dest="doc_ids",
        help="Existing doc_id to evaluate (repeatable). Implies profile lookup.",
    )
    parser.add_argument(
        "--glob",
        default="*.pdf",
        help='Fallback glob when --file/--doc-id omitted (default: "*.pdf").',
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="Cap number of selected docs.",
    )
    parser.add_argument(
        "--queries-only",
        action="store_true",
        help="Skip ingest/embed; only run QueryAgent / AuditAgent on existing indexes.",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="When ingesting: build PageIndex+FactTable but skip Chroma embeddings.",
    )
    parser.add_argument(
        "--ingest-only",
        action="store_true",
        help="Ingest/index only; do not run queries.",
    )
    parser.add_argument(
        "--q1",
        default=None,
        help="Override conceptual question (suite mode).",
    )
    parser.add_argument(
        "--q2",
        default=None,
        help="Override numerical / FactTable question (suite mode).",
    )
    parser.add_argument(
        "--claim",
        default=None,
        help="Override unanswerable audit claim (suite mode; expect unverifiable).",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Run ONLY this QueryAgent question (skips default Q1/Q2/Audit suite).",
    )
    parser.add_argument(
        "--audit",
        default=None,
        help="Run ONLY this AuditAgent claim (skips default suite unless combined with --query).",
    )
    parser.add_argument(
        "--suite",
        action="store_true",
        help="Force the default 3-check suite even when --query/--audit are set.",
    )
    parser.add_argument(
        "--no-tracing",
        action="store_true",
        help="Disable LangSmith for this run.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPORT_PATH,
        help=f"JSON report path (default: {REPORT_PATH})",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    configure_langsmith(enabled=False if args.no_tracing else None)

    data_dir = args.data_dir
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir

    try:
        targets = select_targets(
            data_dir,
            files=args.files,
            doc_ids=args.doc_ids,
            pattern=args.glob,
            max_docs=args.max_docs,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    if not targets:
        print(f"No documents selected under {data_dir}")
        return 1

    # If user passes --query/--audit without --suite, skip auto suite.
    run_suite = True
    if (args.query or args.audit) and not args.suite:
        run_suite = False
    plan = EvalPlan(
        run_suite=run_suite and not args.ingest_only,
        q1=args.q1,
        q2=args.q2,
        claim=args.claim,
        custom_query=args.query,
        custom_audit=args.audit,
    )
    # ingest-only: no queries at all
    if args.ingest_only:
        plan = EvalPlan(run_suite=False)

    print(f"Corpus dir : {data_dir}")
    print(f"Selected   : {len(targets)} document(s)")
    for label, pdf, prof in targets:
        print(
            f"  - {label}"
            + (f"  path={pdf}" if pdf else "")
            + (f"  doc_id={prof.doc_id}" if prof else "")
        )
    mode = []
    if args.queries_only:
        mode.append("queries-only")
    if args.skip_embed:
        mode.append("skip-embed")
    if args.ingest_only:
        mode.append("ingest-only")
    if args.query:
        mode.append(f"custom-query={args.query[:60]!r}")
    if args.audit:
        mode.append(f"custom-audit={args.audit[:60]!r}")
    if plan.run_suite:
        mode.append("suite=Q1+Q2+Audit")
    print(f"Mode       : {', '.join(mode) or 'full suite'}")

    results: list[DocumentEvalResult] = []
    for i, (label, pdf, profile) in enumerate(targets, 1):
        print("-" * 72)
        print(f"[{i}/{len(targets)}] {label}")
        row = evaluate_document(
            label=label,
            pdf_path=pdf,
            existing_profile=profile,
            queries_only=args.queries_only,
            skip_embed=args.skip_embed,
            skip_queries=args.ingest_only,
            plan=plan,
        )
        results.append(row)
        if row.ingest_error:
            print(f"  ERROR: {row.ingest_error}")
        else:
            print(
                f"  doc_id={row.doc_id} tier={row.triage_tier} "
                f"pages={row.page_count} chunks={row.chunks_generated} "
                f"facts={row.facts_written}"
            )
            for q in row.queries:
                print(f"  [{q.kind}] {q.status}: {_clip(q.query, 70)}")

    report = CorpusEvaluationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_dir=str(data_dir),
        pdf_count=len(discover_pdfs(data_dir)),
        docs_attempted=len(results),
        docs_succeeded=sum(1 for d in results if not d.ingest_error),
        options={
            "files": args.files,
            "doc_ids": args.doc_ids,
            "glob": args.glob,
            "max_docs": args.max_docs,
            "skip_embed": args.skip_embed,
            "queries_only": args.queries_only,
            "ingest_only": args.ingest_only,
            "q1": args.q1,
            "q2": args.q2,
            "claim": args.claim,
            "query": args.query,
            "audit": args.audit,
            "suite": plan.run_suite,
            "no_tracing": args.no_tracing,
        },
        documents=results,
    )
    out = save_report(report, args.report)
    print_summary_table(results)
    print(f"Detailed report saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
