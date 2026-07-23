"""Offline unit tests for the LangGraph Query Agent (no live API calls)."""

from __future__ import annotations

from pathlib import Path

from src.agents.query_agent import (
    QueryAgent,
    QueryAgentDeps,
    _default_plan,
    _expand_cite_indices,
    _extract_json,
)
from src.chunking.models import DocumentChunk
from src.facts.extractor import extract_and_store
from src.facts.store import FactStore
from src.llm.base import LLMClient, LLMResult
from src.models.provenance import ProvenanceChain
from src.models.query import QueryAnswer, ToolName
from src.pageindex.builder import build_page_index, save_page_index
from src.query.evidence import EvidenceHit
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
    """Returns canned JSON strings in order (planner, then synthesizer, ...)."""

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


def test_extract_json_and_default_plan():
    assert _extract_json('{"calls":[]}') == {"calls": []}
    assert "calls" not in _extract_json("not json")
    plan = _default_plan("What was import tax expenditure in FY 2020/21?")
    tools = [c["tool"] for c in plan]
    assert "semantic_search" in tools
    assert "structured_query" in tools
    semantic = next(c for c in plan if c["tool"] == "semantic_search")
    assert semantic["args"]["top_k"] == 7


def test_expand_cite_indices_pads_to_min_and_max():
    hits = [
        EvidenceHit(
            tool=ToolName.SEMANTIC_SEARCH,
            page_number=i + 1,
            excerpt=f"e{i}",
            content_hash=f"h{i}",
            score=float(10 - i),
        )
        for i in range(7)
    ]
    # Synthesizer only cited the first item -> pad with next-best by score.
    expanded = _expand_cite_indices(
        [0], hits, min_citations=5, max_citations=7
    )
    assert expanded[0] == 0
    assert len(expanded) == 7
    assert set(expanded) == set(range(7))

    # Cap at max_citations even when more hits exist.
    capped = _expand_cite_indices(
        [2], hits, min_citations=5, max_citations=5
    )
    assert len(capped) == 5
    assert capped[0] == 2


def test_query_agent_offline_end_to_end(tmp_path: Path):
    """Full graph with fake LLM + local stores; zero network / API spend."""
    chunks = [
        _chunk(
            "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
            ["Executive summary"],
            [4],
        ),
        _chunk("Board governance notes only.", ["Governance"], [10]),
    ]
    index = build_page_index(
        chunks, doc_id="qdoc", source_filename="sample.pdf",
        summarize=True, llm_client=None,
    )
    save_page_index(index, directory=tmp_path / "pageindex")

    chroma = ChromaLDUStore(persist_dir=tmp_path / "chroma", collection_name="qdoc")
    embedder = _FakeEmbedder()
    ingest_chunks(
        chunks, doc_id="qdoc", document_name="sample.pdf",
        store=chroma, embedder=embedder,
    )

    facts = FactStore(tmp_path / "facts.db")
    extract_and_store(chunks, doc_id="qdoc", document_name="sample.pdf", store=facts)

    plan_json = (
        '{"calls":['
        '{"tool":"semantic_search","args":{"query":"import tax expenditures","top_k":3}},'
        '{"tool":"structured_query","args":{"metric_contains":"Import tax","limit":5}}'
        "]}"
    )
    llm = _ScriptedLLM(
        [
            plan_json,
            (
                '{"answer":"Import tax expenditures were ETB 120.7 billion in FY 2020/21.",'
                '"cite_indices":[0],"refusal":false}'
            ),
        ]
    )

    agent = QueryAgent(
        QueryAgentDeps(
            llm=llm,
            doc_id="qdoc",
            pdf_path=None,
            pageindex_dir=tmp_path / "pageindex",
            chroma_store=chroma,
            embedder=embedder,
            fact_store=facts,
            max_tool_calls=3,
        )
    )
    answer = agent.ask("What was import tax expenditure in FY 2020/21?")
    assert isinstance(answer, QueryAnswer)
    assert "120.7" in answer.answer
    assert not answer.provenance.is_empty
    assert answer.doc_id == "qdoc"
    assert len(llm.calls) == 2  # plan + synthesize only
    assert any(t.tool.value == "semantic_search" for t in answer.tool_trace)


def test_query_agent_refusal_when_no_evidence(tmp_path: Path):
    llm = _ScriptedLLM(
        [
            '{"calls":[{"tool":"semantic_search","args":{"query":"mars revenue"}}]}',
            '{"answer":"I could not find that in the document.","cite_indices":[],"refusal":true}',
        ]
    )
    chroma = ChromaLDUStore(persist_dir=tmp_path / "chroma", collection_name="empty")
    agent = QueryAgent(
        QueryAgentDeps(
            llm=llm,
            doc_id="missing",
            pdf_path=None,
            pageindex_dir=tmp_path / "pageindex",
            chroma_store=chroma,
            embedder=_FakeEmbedder(),
            fact_store=FactStore(tmp_path / "facts.db"),
        )
    )
    answer = agent.ask("What was revenue on Mars?")
    assert answer.provenance == ProvenanceChain() or answer.provenance.is_empty
    assert "could not find" in answer.answer.lower()
