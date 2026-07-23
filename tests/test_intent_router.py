"""Offline tests for STEP 2 IntentRouter + federated Chroma filtering."""

from __future__ import annotations

from pathlib import Path

from src.agents.intent_router import _heuristic_route, list_corpus_documents, route_intent
from src.agents.query_agent import QueryAgent, QueryAgentDeps
from src.chunking.models import DocumentChunk
from src.facts.store import FactStore
from src.llm.base import LLMClient, LLMResult
from src.models.intent import CorpusDocument, IntentRouter, SearchScope
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


def test_intent_router_schema_aligns_scope():
    pinned = IntentRouter(document_id="abc", rationale="named")
    assert pinned.scope is SearchScope.SINGLE_DOCUMENT
    assert not pinned.is_corpus_wide

    wide = IntentRouter(document_id=None, rationale="general")
    assert wide.scope is SearchScope.CORPUS
    assert wide.is_corpus_wide


def test_heuristic_routes_by_filename():
    docs = [
        CorpusDocument(document_id="d1", document_name="sample.pdf"),
        CorpusDocument(document_id="d2", document_name="audit-findings.pdf"),
    ]
    hit = _heuristic_route("What does the audit-findings report say?", docs)
    assert hit.document_id == "d2"

    wide = _heuristic_route("Summarize all revenue figures across reports", docs)
    assert wide.document_id is None


def test_forced_document_skips_llm():
    llm = _ScriptedLLM(['{"document_id":null}'])
    intent = route_intent(
        "anything",
        corpus=[CorpusDocument(document_id="x", document_name="x.pdf")],
        llm=llm,
        forced_document_id="212dc42370e2",
    )
    assert intent.document_id == "212dc42370e2"
    assert intent.confidence == 1.0
    assert llm.calls == []


def test_chroma_metadata_filter_vs_corpus(tmp_path: Path):
    store = ChromaLDUStore(persist_dir=tmp_path / "chroma", collection_name="fed")
    embedder = _FakeEmbedder()
    ingest_chunks(
        [_chunk("Alpha revenue was 10.", ["A"], [1])],
        doc_id="docA",
        document_name="alpha.pdf",
        store=store,
        embedder=embedder,
    )
    ingest_chunks(
        [_chunk("Beta revenue was 99.", ["B"], [1])],
        doc_id="docB",
        document_name="beta.pdf",
        store=store,
        embedder=embedder,
    )

    from src.retrieval.ingest import semantic_search

    scoped = semantic_search(
        "revenue", doc_id="docA", top_k=5, store=store, embedder=embedder
    )
    assert scoped
    assert all(h.doc_id == "docA" for h in scoped)

    wide = semantic_search(
        "revenue", doc_id=None, top_k=5, store=store, embedder=embedder
    )
    ids = {h.doc_id for h in wide}
    assert "docA" in ids and "docB" in ids


def test_agent_route_then_retrieve_corpus(tmp_path: Path):
    store = ChromaLDUStore(persist_dir=tmp_path / "chroma", collection_name="fed2")
    embedder = _FakeEmbedder()
    ingest_chunks(
        [_chunk("Import tax expenditures were ETB 120.7 billion.", ["Exec"], [4])],
        doc_id="taxdoc",
        document_name="tax.pdf",
        store=store,
        embedder=embedder,
    )
    ingest_chunks(
        [_chunk("Martian mining revenue was fictional.", ["Space"], [1])],
        doc_id="spacedoc",
        document_name="mars.pdf",
        store=store,
        embedder=embedder,
    )
    corpus = [
        CorpusDocument(document_id="taxdoc", document_name="tax.pdf"),
        CorpusDocument(document_id="spacedoc", document_name="mars.pdf"),
    ]
    # No forced doc_id => router LLM runs first, then plan, then synthesize.
    llm = _ScriptedLLM(
        [
            '{"document_id":null,"confidence":0.8,"rationale":"general question"}',
            '{"calls":[{"tool":"semantic_search","args":{"query":"import tax","top_k":5}}]}',
            (
                '{"answer":"Import tax expenditures were ETB 120.7 billion.",'
                '"cite_indices":[0],"refusal":false}'
            ),
        ]
    )
    agent = QueryAgent(
        QueryAgentDeps(
            llm=llm,
            doc_id=None,
            chroma_store=store,
            embedder=embedder,
            fact_store=FactStore(tmp_path / "facts.db"),
            pageindex_dir=tmp_path / "pageindex",
            corpus=corpus,
        )
    )
    answer = agent.ask("What was import tax expenditure?")
    assert "120.7" in answer.answer
    assert not answer.provenance.is_empty
    assert len(llm.calls) == 3


def test_list_corpus_documents_reads_profiles():
    docs = list_corpus_documents()
    # May be empty in CI without profiles; just ensure it returns a list.
    assert isinstance(docs, list)
