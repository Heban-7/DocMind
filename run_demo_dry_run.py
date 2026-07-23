"""
DocMind | Phase 4 offline demo dry-run (no live API calls).

Exercises the full query path with FakeLLM + FakeEmbedder:
  chunks -> PageIndex + FactTable + Chroma -> ask + audit

Usage:
    uv run python run_demo_dry_run.py
"""

from __future__ import annotations

from pathlib import Path

from src.agents.audit_agent import AuditAgent, AuditAgentDeps
from src.agents.query_agent import QueryAgent, QueryAgentDeps
from src.chunking.models import DocumentChunk
from src.config import CHUNKS_DIR, DEFAULT_SAMPLE_PDF, PROJECT_ROOT
from src.facts.store import FactStore
from src.llm.base import LLMClient, LLMResult
from src.models.query import AuditStatus
from src.pageindex.builder import load_chunks_jsonl
from src.pipeline.phase4 import build_query_indexes
from src.retrieval.vector_store import ChromaLDUStore


class FakeEmbedder:
    model = "fake-demo"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            base = [0.0] * 8
            for i, ch in enumerate(text.lower()[:64]):
                base[i % 8] += (ord(ch) % 31) / 31.0
            norm = sum(v * v for v in base) ** 0.5 or 1.0
            out.append([v / norm for v in base])
        return out


class ScriptedLLM(LLMClient):
    provider = "fake"

    def __init__(self, scripts: list[str]):
        super().__init__(model="fake-demo")
        self._scripts = list(scripts)

    def chat(self, messages, *, response_format=None, temperature=None, max_tokens=None):
        text = self._scripts.pop(0) if self._scripts else "{}"
        return LLMResult(text=text, model=self.model, provider=self.provider)


DEMO_CHUNKS = [
    DocumentChunk.create(
        "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
        parent_hierarchy=["Executive summary"],
        page_numbers=[4],
        chunk_type="prose",
    ),
    DocumentChunk.create(
        "Domestic revenue mobilization remained a policy priority.",
        parent_hierarchy=["Revenue"],
        page_numbers=[12],
        chunk_type="prose",
    ),
]


def _load_or_seed_chunks(work: Path) -> tuple[str, str, Path]:
    """Prefer a tiny seeded corpus so the dry-run stays fast and deterministic."""
    doc_id = "demo_offline"
    name = "demo.pdf"
    chunks_dir = work / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    path = chunks_dir / f"{doc_id}.jsonl"
    path.write_text(
        "\n".join(c.model_dump_json() for c in DEMO_CHUNKS) + "\n",
        encoding="utf-8",
    )
    return doc_id, name, chunks_dir


def run_offline_demo(work_dir: Path | None = None) -> dict:
    """Run ask + audit offline. Returns a small result dict for tests/printing."""
    work = work_dir or (PROJECT_ROOT / ".refinery" / "_demo_offline")
    work.mkdir(parents=True, exist_ok=True)

    doc_id, document_name, chunks_dir = _load_or_seed_chunks(work)
    chroma = ChromaLDUStore(
        persist_dir=work / "chroma", collection_name="demo_offline"
    )
    facts = FactStore(work / "facts.db")
    embedder = FakeEmbedder()

    index_result = build_query_indexes(
        doc_id,
        document_name=document_name,
        chunks_dir=chunks_dir,
        embed=True,
        pageindex_llm_client=None,
        chroma_store=chroma,
        fact_store=facts,
        embedder=embedder,
    )

    pdf_path = DEFAULT_SAMPLE_PDF if DEFAULT_SAMPLE_PDF.exists() else None

    ask_llm = ScriptedLLM(
        [
            (
                '{"calls":[{"tool":"semantic_search",'
                '"args":{"query":"import tax expenditures","top_k":3}},'
                '{"tool":"structured_query",'
                '"args":{"metric_contains":"Import tax","limit":5}}]}'
            ),
            (
                '{"answer":"Import tax expenditures were ETB 120.7 billion in FY 2020/21.",'
                '"cite_indices":[0],"refusal":false}'
            ),
        ]
    )
    query_agent = QueryAgent(
        QueryAgentDeps(
            llm=ask_llm,
            doc_id=doc_id,
            pdf_path=pdf_path,
            pageindex_dir=index_result.pageindex_path.parent
            if index_result.pageindex_path
            else None,
            chroma_store=chroma,
            embedder=embedder,
            fact_store=facts,
        )
    )
    question = "What was import tax expenditure in FY 2020/21?"
    answer = query_agent.ask(question)

    audit_llm = ScriptedLLM(
        [
            (
                '{"status":"verified",'
                '"rationale":"Evidence states ETB 120.7 billion for FY 2020/21.",'
                '"cite_indices":[0]}'
            ),
            (
                '{"status":"unverifiable",'
                '"rationale":"No evidence supports Martian revenue.",'
                '"cite_indices":[]}'
            ),
        ]
    )
    audit_agent = AuditAgent(
        AuditAgentDeps(
            llm=audit_llm,
            doc_id=doc_id,
            pdf_path=pdf_path,
            pageindex_dir=index_result.pageindex_path.parent
            if index_result.pageindex_path
            else None,
            chroma_store=chroma,
            embedder=embedder,
            fact_store=facts,
            use_planner=False,
        )
    )
    verified = audit_agent.audit(
        "Import tax expenditures were ETB 120.7 billion in FY 2020/21."
    )
    unverifiable = audit_agent.audit("Revenue on Mars was $4.2B in Q3.")

    # Optional: confirm real sample chunks exist (informational only).
    sample_chunks = CHUNKS_DIR / "212dc42370e2.jsonl"
    sample_ready = sample_chunks.exists()
    sample_n = len(load_chunks_jsonl(sample_chunks)) if sample_ready else 0

    return {
        "doc_id": doc_id,
        "chunks_embedded": index_result.chunks_embedded,
        "facts_written": index_result.facts_written,
        "answer": answer.answer,
        "answer_citations": len(answer.provenance),
        "verified_status": verified.status.value,
        "verified_citations": len(verified.provenance),
        "unverifiable_status": unverifiable.status.value,
        "sample_corpus_ready": sample_ready,
        "sample_chunk_count": sample_n,
        "ok": (
            "120.7" in answer.answer
            and len(answer.provenance) >= 1
            and verified.status is AuditStatus.VERIFIED
            and unverifiable.status is AuditStatus.UNVERIFIABLE
        ),
    }


def main() -> int:
    print("=" * 72)
    print("DocMind | Phase 4 offline demo dry-run (no API spend)")
    print("=" * 72)
    result = run_offline_demo()
    print(f"Indexed chunks : {result['chunks_embedded']}")
    print(f"Facts written  : {result['facts_written']}")
    print(f"Ask answer     : {result['answer']}")
    print(f"Ask citations  : {result['answer_citations']}")
    print(f"Audit true     : {result['verified_status']} "
          f"({result['verified_citations']} cites)")
    print(f"Audit false    : {result['unverifiable_status']}")
    if result["sample_corpus_ready"]:
        print(
            f"Live corpus    : 212dc42370e2 ready "
            f"({result['sample_chunk_count']} chunks on disk)"
        )
    print("-" * 72)
    if result["ok"]:
        print("DRY-RUN OK")
        print("=" * 72)
        return 0
    print("DRY-RUN FAILED")
    print("=" * 72)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
