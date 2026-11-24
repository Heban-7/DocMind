"""Offline tests for STEP 1 conversational memory (checkpointer + thread_id).

The Postgres checkpointer itself is covered by tests/test_db_isolation.py.
"""

from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from src.agents.memory import read_messages
from src.agents.query_agent import QueryAgent, QueryAgentDeps
from src.chunking.models import DocumentChunk
from src.facts.extractor import extract_and_store
from src.llm.base import LLMClient, LLMResult
from src.models.conversation import MessageRole, SessionConfig
from src.pageindex.builder import build_page_index
from src.retrieval.ingest import ingest_chunks
from src.stores.memory import memory_stores


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


def test_session_config_runnable_shape():
    cfg = SessionConfig(thread_id="user-42")
    assert cfg.to_runnable_config() == {"configurable": {"thread_id": "user-42"}}


def test_memory_persists_across_turns(tmp_path: Path):
    chunks = [
        _chunk(
            "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
            ["Executive summary"],
            [4],
        ),
    ]
    index = build_page_index(
        chunks, doc_id="memdoc", source_filename="sample.pdf",
        summarize=True, llm_client=None,
    )
    stores = memory_stores()
    stores.pageindex.save(index)
    embedder = _FakeEmbedder()
    ingest_chunks(
        chunks, doc_id="memdoc", document_name="sample.pdf",
        store=stores.chunks, embedder=embedder,
    )
    extract_and_store(chunks, doc_id="memdoc", document_name="sample.pdf", store=stores.facts)

    # Turn 1: no history, so a rule-based plan and one answer call. Turn 2
    # has history: one planning call resolves "that amount", then the answer.
    llm = _ScriptedLLM(
        [
            "Import tax expenditures were ETB 120.7 billion in FY 2020/21 [E1].",
            '{"kind":"question","question":"What was the import tax expenditure amount in FY 2020/21?","facts":null}',
            "As noted earlier, the figure was ETB 120.7 billion [E1].",
        ]
    )
    checkpointer = InMemorySaver()
    agent = QueryAgent(
        QueryAgentDeps(
            llm=llm,
            stores=stores,
            doc_id="memdoc",
            pdf_path=None,
            embedder=embedder,
            checkpointer=checkpointer,
        )
    )

    thread = "demo-thread-1"
    a1 = agent.ask("What was import tax expenditure?", thread_id=thread)
    assert "120.7" in a1.answer

    a2 = agent.ask("Remind me of that amount.", thread_id=thread)
    assert "120.7" in a2.answer

    history = agent.get_messages(thread)
    assert len(history) >= 4  # user, assistant, user, assistant
    assert history[0].role is MessageRole.USER
    assert history[1].role is MessageRole.ASSISTANT
    # The API reads history straight from the checkpointer, without an agent.
    assert [m.content for m in read_messages(checkpointer, thread)] == [m.content for m in history]

    # The second turn's planner and answer saw the earlier conversation.
    assert len(llm.calls) == 3
    assert "recent conversation" in llm.calls[1] and "recent conversation" in llm.calls[2]
    assert "import tax expenditure amount" in llm.calls[2]  # the answer got the standalone question


def test_different_threads_are_isolated(tmp_path: Path):
    checkpointer = InMemorySaver()
    llm = _ScriptedLLM(
        [
            '{"calls":[{"tool":"semantic_search","args":{"query":"x"}}]}',
            '{"answer":"I could not find that in the document.","cite_indices":[],"refusal":true}',
            '{"calls":[{"tool":"semantic_search","args":{"query":"y"}}]}',
            '{"answer":"I could not find that in the document.","cite_indices":[],"refusal":true}',
        ]
    )
    agent = QueryAgent(
        QueryAgentDeps(
            llm=llm,
            stores=memory_stores(),
            doc_id="missing",
            checkpointer=checkpointer,
            embedder=_FakeEmbedder(),
        )
    )
    agent.ask("Hello from A", thread_id="thread-A")
    agent.ask("Hello from B", thread_id="thread-B")
    hist_a = agent.get_messages("thread-A")
    hist_b = agent.get_messages("thread-B")
    assert any("Hello from A" in m.content for m in hist_a)
    assert not any("Hello from A" in m.content for m in hist_b)
    assert any("Hello from B" in m.content for m in hist_b)
