"""Run DocMind as it ships now and capture its raw outputs.

Ingest goes through the product's own ``ingest_document`` into Postgres,
under an evaluation account of its own (one per run folder), and questions go
through the product's Query Agent on the Postgres stores.

``DOCMIND_EVAL_REUSE_MODELS`` may point at a folder of saved document models
(``<sha256[:12]>.json``, as an earlier run wrote them). Matching documents
then skip extraction and reuse that run's extraction time and cost; use it
only when the extraction code has not changed since that run.

V1 and the M2 storage stack are no longer in the tree; to reproduce their
numbers, check out commit 9d8509f and run ``--system v1`` or ``--system v2``.
"""

from __future__ import annotations

import os
import re
import time
import traceback
from pathlib import Path

from evaluation.systems.usage import install, measured

_PAGE_MARK = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.IGNORECASE)
_FAILED_MARK = re.compile(r"<!--\s*pages?\s+(\d+)(?:-(\d+))?\s+failed", re.IGNORECASE)


def split_pages(markdown: str) -> tuple[dict[int, str], set[int]]:
    """Split rendered markdown on its ``<!-- page N -->`` markers."""
    pages: dict[int, str] = {}
    current = 1
    pos = 0
    for m in _PAGE_MARK.finditer(markdown):
        pages[current] = pages.get(current, "") + markdown[pos : m.start()]
        current = int(m.group(1))
        pos = m.end()
    pages[current] = pages.get(current, "") + markdown[pos:]
    failed: set[int] = set()
    for m in _FAILED_MARK.finditer(markdown):
        a = int(m.group(1))
        b = int(m.group(2) or a)
        failed.update(range(a, b + 1))
    return {p: t.strip() for p, t in pages.items()}, failed


def _principal():
    from src.db.local import local_principal

    name = re.sub(r"[^a-z0-9-]+", "-", os.getenv("DOCMIND_EVAL_ACCOUNT", "eval").lower()).strip("-") or "eval"
    return local_principal(f"{name}@eval.docmind.invalid")


def _device() -> str:
    from src.document.device import lanes, resolve_device

    dev, _ = resolve_device()
    return f"{dev.value if hasattr(dev, 'value') else dev} x{lanes()} lanes"


def _reused_model(pdf_path: Path):
    folder = os.getenv("DOCMIND_EVAL_REUSE_MODELS")
    if not folder:
        return None
    from src.document.model import DocumentModel
    from src.pipeline.ingest import sha256_file

    path = Path(folder) / f"{sha256_file(pdf_path)[:12]}.json"
    if not path.exists():
        return None
    return DocumentModel.model_validate_json(path.read_text(encoding="utf-8"))


def run_document(pdf_path: Path, *, embed: bool = True) -> dict:
    """Ingest one PDF through the product pipeline. Returns raw outputs."""
    install()
    from src.db.migrate import migrate
    from src.document.render import render_markdown
    from src.pipeline.ingest import ingest_document
    from src.storage.blobs import get_blob_store
    from src.stores.pg import pg_stores

    out: dict = {"file": pdf_path.name, "device": _device(), "error": None, "stages": {}}
    try:
        migrate()
        principal = _principal()
        reused = _reused_model(pdf_path)
        with measured() as m:
            result = ingest_document(pdf_path, principal=principal, embed=embed, model=reused)
        seconds = (result.stats or {}).get("seconds") or {}
        if reused is not None:
            out["stages"]["extract"] = {"seconds": reused.seconds, "total_cost_usd": reused.cost_usd, "reused": True}
        else:
            out["stages"]["extract"] = {
                "seconds": seconds.get("extract", 0.0),
                "total_cost_usd": (result.stats or {}).get("extraction_cost_usd", 0.0),
            }
        index_seconds = sum(seconds.get(k, 0.0) for k in ("chunk", "index", "embed"))
        out["stages"]["index"] = {
            "seconds": index_seconds,
            "storage_seconds": max(0.0, m["seconds"] - index_seconds - (0.0 if reused else seconds.get("extract", 0.0))),
            "total_cost_usd": m.get("embed_cost_usd", 0.0),
            "embed_calls": m.get("embed_calls", 0),
        }
        out.update(
            doc_id=result.document_id,
            n_pages=result.page_count,
            chunks=result.chunk_count,
            facts_written=result.facts_written,
            pages_needing_review=result.pages_needing_review,
            deduplicated=result.deduplicated,
            engine="structured_v2 " + ", ".join(f"{k}:{v}" for k, v in (result.engines or {}).items()),
        )

        # Read back what Postgres and the blob store now hold, as a user would get it.
        from src.db import repos
        from src.document.model import DocumentModel

        doc = repos.require_document(principal.tenant_id, result.document_id)
        model = DocumentModel.model_validate_json(
            get_blob_store().local_path(doc.model_key).read_text(encoding="utf-8")
        )
        pages, failed = split_pages(render_markdown(model))
        out["pages_text"] = {str(k): v for k, v in pages.items()}
        out["failed_pages"] = sorted(failed)
        out["ledger"] = model.ledger()
        facts = pg_stores(principal.tenant_id).facts.search(doc_id=result.document_id, limit=1_000_000)
        out["facts"] = [
            {
                "metric": f.metric,
                "value": f.value,
                "value_text": f.value_text,
                "unit": f.unit,
                "period": f.period,
                "page_number": f.page_number,
            }
            for f in facts
        ]
    except Exception as exc:  # record and continue with the next document
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()[-2000:]
    out["total_seconds"] = round(sum(s.get("seconds", 0.0) for s in out["stages"].values()), 2)
    return out


def ask(doc_id: str, pdf_path: Path, question: str, *, model: str | None = None) -> dict:  # noqa: ARG001
    """Ask one question about one document through the product's agent."""
    install()
    from src.agents.query_agent import build_query_agent
    from src.db import repos
    from src.llm.factory import get_text_client
    from src.retrieval.ingest import semantic_search
    from src.storage.blobs import get_blob_store
    from src.stores.pg import pg_stores

    principal = _principal()
    stores = pg_stores(principal.tenant_id)
    blobs = get_blob_store()

    def resolver(did: str):
        doc = repos.get_document(principal.tenant_id, did)
        return blobs.local_path(doc.storage_key) if doc else None

    llm = get_text_client(model=model) if model else None
    agent = build_query_agent(doc_id, stores=stores, llm=llm, pdf_resolver=resolver)
    start = time.perf_counter()
    with measured() as m:
        answer = agent.ask(question)
    latency = time.perf_counter() - start
    with measured() as r:
        hits = semantic_search(question, doc_id=doc_id, top_k=5, store=stores.chunks)
    return {
        "answer": answer.answer,
        "cited_pages": [c.page_number for c in answer.provenance.citations],
        "tools": [t.tool.value for t in answer.tool_trace],
        "latency_s": round(latency, 3),
        "first_token_s": round(latency, 3),  # answers are not streamed token by token yet
        "usage": m,
        "retrieval_top5_pages": sorted({p for h in hits for p in (h.page_numbers or [])}),
        "retrieval_usage": r,
    }
