"""Offline unit tests for Audit Mode (no live API calls)."""

from __future__ import annotations

from pathlib import Path

from src.agents.audit_agent import AuditAgent, AuditAgentDeps
from src.chunking.models import DocumentChunk
from src.facts.extractor import extract_and_store
from src.facts.store import FactStore
from src.llm.base import LLMClient, LLMResult
from src.models.query import AuditStatus, AuditVerdict
from src.pageindex.builder import build_page_index, save_page_index
from src.retrieval.ingest import ingest_chunks
from src.retrieval.vector_store import ChromaLDUStore


class _FakeEmbedder:
    model = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            base = [0.0] * 8
            for i, ch in enumerate(text.lower()[:64]):
                base[i % 8] += (ord(ch) % 31) / 31.0
            norm = sum(v * v for v in base) ** 0.5 or 1.0
            out.append([v / norm for v in base])
        return out


class _ScriptedLLM(LLMClient):
    provider = "fake"

    def __init__(self, scripts: list[str]):
        super().__init__(model="fake-script")
        self._scripts = list(scripts)
        self.calls: list[str] = []

    def chat(self, messages, *, response_format=None, temperature=None, max_tokens=None):
        prompt = ""
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                prompt += content
        self.calls.append(prompt)
        text = self._scripts.pop(0) if self._scripts else "{}"
        return LLMResult(text=text, model=self.model, provider=self.provider)


def _chunk(text: str, hierarchy: list[str], pages: list[int]) -> DocumentChunk:
    return DocumentChunk.create(
        text, parent_hierarchy=hierarchy, page_numbers=pages, chunk_type="prose"
    )


def _build_stores(tmp_path: Path):
    chunks = [
        _chunk(
            "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
            ["Executive summary"],
            [4],
        ),
        _chunk("Board governance notes only.", ["Governance"], [10]),
    ]
    index = build_page_index(
        chunks, doc_id="adoc", source_filename="sample.pdf",
        summarize=True, llm_client=None,
    )
    save_page_index(index, directory=tmp_path / "pageindex")
    chroma = ChromaLDUStore(persist_dir=tmp_path / "chroma", collection_name="adoc")
    embedder = _FakeEmbedder()
    ingest_chunks(
        chunks, doc_id="adoc", document_name="sample.pdf",
        store=chroma, embedder=embedder,
    )
    facts = FactStore(tmp_path / "facts.db")
    extract_and_store(chunks, doc_id="adoc", document_name="sample.pdf", store=facts)
    return chroma, embedder, facts


def test_audit_verified_offline(tmp_path: Path):
    chroma, embedder, facts = _build_stores(tmp_path)
    llm = _ScriptedLLM(
        [
            (
                '{"status":"verified",'
                '"rationale":"Exact ETB 120.7 billion figure appears in evidence.",'
                '"cite_indices":[0]}'
            )
        ]
    )
    agent = AuditAgent(
        AuditAgentDeps(
            llm=llm,
            doc_id="adoc",
            pdf_path=None,
            pageindex_dir=tmp_path / "pageindex",
            chroma_store=chroma,
            embedder=embedder,
            fact_store=facts,
            use_planner=False,
        )
    )
    verdict = agent.audit(
        "Import tax expenditures were ETB 120.7 billion in FY 2020/21."
    )
    assert isinstance(verdict, AuditVerdict)
    assert verdict.status is AuditStatus.VERIFIED
    assert not verdict.provenance.is_empty
    assert len(llm.calls) == 1  # judge only; no planner


def test_audit_unverifiable_offline(tmp_path: Path):
    chroma, embedder, facts = _build_stores(tmp_path)
    llm = _ScriptedLLM(
        [
            (
                '{"status":"unverifiable",'
                '"rationale":"No evidence of Martian revenue.",'
                '"cite_indices":[]}'
            )
        ]
    )
    agent = AuditAgent(
        AuditAgentDeps(
            llm=llm,
            doc_id="adoc",
            pdf_path=None,
            pageindex_dir=tmp_path / "pageindex",
            chroma_store=chroma,
            embedder=embedder,
            fact_store=facts,
            use_planner=False,
        )
    )
    verdict = agent.audit("Revenue on Mars was $4.2B in Q3.")
    assert verdict.status is AuditStatus.UNVERIFIABLE
    assert verdict.provenance.is_empty
    assert "Mars" in verdict.rationale or "evidence" in verdict.rationale.lower()


def test_audit_forces_unverifiable_without_cites(tmp_path: Path):
    chroma, embedder, facts = _build_stores(tmp_path)
    # Model wrongly says verified with empty cites -> agent must demote.
    llm = _ScriptedLLM(
        [
            '{"status":"verified","rationale":"Looks fine","cite_indices":[]}'
        ]
    )
    agent = AuditAgent(
        AuditAgentDeps(
            llm=llm,
            doc_id="adoc",
            pdf_path=None,
            pageindex_dir=tmp_path / "pageindex",
            chroma_store=chroma,
            embedder=embedder,
            fact_store=facts,
            use_planner=False,
        )
    )
    verdict = agent.audit("Import tax expenditures were ETB 120.7 billion.")
    assert verdict.status is AuditStatus.UNVERIFIABLE
    assert verdict.provenance.is_empty


def test_audit_empty_claim_no_llm():
    llm = _ScriptedLLM(["should not be called"])
    agent = AuditAgent(
        AuditAgentDeps(llm=llm, doc_id="x", use_planner=False)
    )
    verdict = agent.audit("   ")
    assert verdict.status is AuditStatus.UNVERIFIABLE
    assert llm.calls == []
