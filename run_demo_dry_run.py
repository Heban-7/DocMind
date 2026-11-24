"""
DocMind | Phase 4 offline demo dry-run (no live API calls).

Exercises the full query path with FakeLLM + FakeEmbedder and in-memory
stores (no database needed):
  chunks -> PageIndex + FactTable + vectors -> ask + audit

Usage:
    uv run python run_demo_dry_run.py
"""

from __future__ import annotations

from pathlib import Path

from src.agents.audit_agent import AuditAgent, AuditAgentDeps
from src.agents.query_agent import QueryAgent, QueryAgentDeps
from src.chunking.models import DocumentChunk
from src.config import DEFAULT_SAMPLE_PDF
from src.facts.extractor import extract_and_store
from src.llm.base import LLMClient, LLMResult
from src.models.query import AuditStatus
from src.pageindex.builder import build_page_index
from src.retrieval.ingest import ingest_chunks
from src.stores.memory import memory_stores


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
    """Canned replies; ``{E:120.7}`` becomes the id of the evidence that contains "120.7"."""

    provider = "fake"

    def __init__(self, scripts: list[str]):
        super().__init__(model="fake-demo")
        self._scripts = list(scripts)

    def _chat(self, messages, **params):
        import re

        text = self._scripts.pop(0) if self._scripts else "{}"
        prompt = str(messages[-1].get("content") or "")
        blocks = re.findall(r'<evidence id="(E[0-9]+)"[^>]*>(.*?)</evidence>', prompt, re.S)

        def cite(m: re.Match) -> str:
            return "[" + next((eid for eid, body in blocks if m.group(1) in body), "E1") + "]"

        text = re.sub(r"\{E:([^}]+)\}", cite, text)
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


def run_offline_demo(work_dir: Path | None = None) -> dict:  # noqa: ARG001 (kept for the old signature)
    """Run ask + audit offline. Returns a small result dict for tests/printing."""
    doc_id, document_name = "demo_offline", "demo.pdf"
    stores = memory_stores()
    embedder = FakeEmbedder()
    stores.pageindex.save(
        build_page_index(DEMO_CHUNKS, doc_id=doc_id, source_filename=document_name, summarize=True, llm_client=None)
    )
    facts = extract_and_store(DEMO_CHUNKS, doc_id=doc_id, document_name=document_name, store=stores.facts)
    embedded = ingest_chunks(
        DEMO_CHUNKS, doc_id=doc_id, document_name=document_name, store=stores.chunks, embedder=embedder
    )

    pdf_path = DEFAULT_SAMPLE_PDF if DEFAULT_SAMPLE_PDF.exists() else None

    # a first question about one document: a rule-based plan, then one answer call
    ask_llm = ScriptedLLM(["Import tax expenditures were ETB 120.7 billion in FY 2020/21 {E:120.7}."])
    query_agent = QueryAgent(
        QueryAgentDeps(
            llm=ask_llm,
            stores=stores,
            doc_id=doc_id,
            pdf_path=pdf_path,
            embedder=embedder,
        )
    )
    question = "What was import tax expenditure in FY 2020/21?"
    answer = query_agent.ask(question)

    audit_llm = ScriptedLLM(
        [
            "Verified: the document states import tax expenditures of ETB 120.7 billion in FY 2020/21 {E:120.7}.",
            "Not found in the document: any revenue on Mars.",
        ]
    )
    audit_agent = AuditAgent(
        AuditAgentDeps(
            llm=audit_llm,
            stores=stores,
            doc_id=doc_id,
            pdf_path=pdf_path,
            embedder=embedder,
            use_planner=False,
        )
    )
    verified = audit_agent.audit(
        "Import tax expenditures were ETB 120.7 billion in FY 2020/21."
    )
    unverifiable = audit_agent.audit("Revenue on Mars was $4.2B in Q3.")

    return {
        "doc_id": doc_id,
        "chunks_embedded": embedded.chunks_ingested,
        "facts_written": facts.facts_written,
        "answer": answer.answer,
        "answer_citations": len(answer.provenance),
        "verified_status": verified.status.value,
        "verified_citations": len(verified.provenance),
        "unverifiable_status": unverifiable.status.value,
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
