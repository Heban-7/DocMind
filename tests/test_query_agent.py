"""Offline tests for the answer engine (no live API calls)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.planning import rules_plan
from src.agents.query_agent import QueryAgent, QueryAgentDeps, StreamFilter, display_text, split_follow_ups
from src.chunking.models import DocumentChunk
from src.facts.extractor import extract_and_store
from src.llm.base import LLMClient, LLMResult
from src.llm.errors import LLMError
from src.models.query import QueryAnswer
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
    """Returns canned replies in order (plan, then answer, ...)."""

    provider = "fake"

    def __init__(self, scripts: list[str]):
        super().__init__(model="fake-script")
        self._scripts = list(scripts)
        self.calls: list[str] = []

    def _chat(self, messages, **params):
        prompt = "".join(m["content"] for m in messages if isinstance(m.get("content"), str))
        self.calls.append(prompt)
        text = self._scripts.pop(0) if self._scripts else "{}"
        return LLMResult(text=text, model=self.model, provider=self.provider, input_tokens=100, output_tokens=20)


class _FailingLLM(LLMClient):
    provider = "fake"

    def __init__(self):
        super().__init__(model="down")

    def _chat(self, messages, **params):
        raise LLMError("ReadTimeout after 3 attempt(s)", kind="timeout", provider="fake")


def _chunk(text: str, hierarchy: list[str], pages: list[int]) -> DocumentChunk:
    return DocumentChunk.create(text, parent_hierarchy=hierarchy, page_numbers=pages, chunk_type="prose")


def _stores():
    chunks = [
        _chunk("Import tax expenditures were ETB 120.7 billion in FY 2020/21.", ["Executive summary"], [4]),
        _chunk("Board governance notes only. General inflation in Ethiopia was 13.6 percent.", ["Governance"], [10]),
    ]
    stores = memory_stores()
    stores.pageindex.save(build_page_index(chunks, doc_id="qdoc", source_filename="sample.pdf", summarize=True, llm_client=None))
    embedder = _FakeEmbedder()
    ingest_chunks(chunks, doc_id="qdoc", document_name="sample.pdf", store=stores.chunks, embedder=embedder)
    extract_and_store(chunks, doc_id="qdoc", document_name="sample.pdf", store=stores.facts)
    return stores, embedder


def _agent(llm, *, planner="auto", doc_id="qdoc", stores=None, embedder=None):
    if stores is None:
        stores, embedder = _stores()
    return QueryAgent(QueryAgentDeps(llm=llm, stores=stores, doc_id=doc_id, embedder=embedder or _FakeEmbedder(), planner=planner))


def _evidence_id(prompt: str, needle: str) -> str:
    """The [E#] of the evidence block that contains ``needle``."""
    import re

    for m in re.finditer(r'<evidence id="(E\d+)"[^>]*>\n(.*?)\n</evidence>', prompt, re.S):
        if needle in m.group(2):
            return m.group(1)
    raise AssertionError(f"{needle!r} not in the evidence")


def test_first_question_takes_one_model_call_and_cites_the_right_page():
    llm = _ScriptedLLM([])
    agent = _agent(llm)
    # the answer is scripted after we see the prompt: answer with the id of the right evidence
    original = llm._chat

    def chat(messages, **kw):
        prompt = messages[-1]["content"]
        eid = _evidence_id(prompt, "120.7 billion")
        llm._scripts = [f"Import tax expenditures were ETB 120.7 billion in FY 2020/21 [{eid}].\n\nFOLLOW-UPS:\n- What changed?"]
        return original(messages, **kw)

    llm._chat = chat
    answer = agent.ask("What was import tax expenditure in FY 2020/21?")
    assert isinstance(answer, QueryAnswer)
    assert answer.status == "answered"
    assert "120.7" in answer.answer and "[Page 4]" in answer.answer and "[E" not in answer.answer
    assert [c.page_number for c in answer.provenance.citations] == [4]  # no padding
    assert answer.follow_ups == ["What changed?"]
    assert len(llm.calls) == 1  # rule-based plan, then one answer call
    assert answer.usage["llm_calls"] == 1 and answer.prompt_profile == "answer-v2.0"
    assert answer.verification["supported"] == 1


def test_llm_planner_is_one_call_and_its_fact_spec_is_used():
    llm = _ScriptedLLM(
        [
            '{"kind":"question","question":"What was import tax expenditure in FY 2020/21?",'
            '"facts":{"op":"lookup","metric":"import tax expenditures","periods":["2020/21"]},"section":null}',
            "Import tax expenditures were ETB 120.7 billion [E1].\nFOLLOW-UPS: none",
        ]
    )
    answer = _agent(llm, planner="llm").ask("What was import tax expenditure in FY 2020/21?")
    assert len(llm.calls) == 2
    assert any(t.tool.value == "structured_query" for t in answer.tool_trace)
    assert answer.verification["plan"]["source"] == "llm"
    assert answer.follow_ups == []


def test_invented_number_is_removed():
    llm = _ScriptedLLM([])
    agent = _agent(llm)
    original = llm._chat

    def chat(messages, **kw):
        eid = _evidence_id(messages[-1]["content"], "120.7 billion")
        llm._scripts = [f"Import tax expenditures were ETB 120.7 billion [{eid}]. The company had 49.5 million subscribers [{eid}]."]
        return original(messages, **kw)

    llm._chat = chat
    answer = agent.ask("What was import tax expenditure in FY 2020/21?")
    assert "120.7" in answer.answer
    assert "49.5" not in answer.answer
    assert answer.verification["removed"] == 1 and answer.verification["numbers_unsupported"] == 1


def test_answer_about_an_entity_the_evidence_never_mentions_becomes_not_found():
    llm = _ScriptedLLM([])
    agent = _agent(llm)
    original = llm._chat

    def chat(messages, **kw):
        prompt = messages[-1]["content"]
        assert "evidence: Kenya." in prompt  # the answer step is told up front
        eid = _evidence_id(prompt, "13.6 percent")
        llm._scripts = [f"The inflation rate for Kenya was 13.6% [{eid}]."]
        return original(messages, **kw)

    llm._chat = chat
    answer = agent.ask("What was the inflation rate for Kenya according to this bulletin?")
    assert answer.status == "not_found"
    assert answer.answer.startswith("Not found in the document")
    assert answer.provenance.is_empty


def test_no_evidence_means_no_answer_call():
    llm = _ScriptedLLM([])
    agent = _agent(llm, doc_id="missing", stores=memory_stores())
    answer = agent.ask("What was revenue on Mars?")
    assert answer.status == "not_found"
    assert llm.calls == []


def test_provider_failure_is_an_error_not_a_refusal():
    with pytest.raises(LLMError) as info:
        _agent(_FailingLLM()).ask("What was import tax expenditure in FY 2020/21?")
    assert info.value.kind == "timeout"


def test_tokens_stream_with_page_badges_and_without_the_trailer():
    llm = _ScriptedLLM([])
    agent = _agent(llm)
    original = llm._chat

    def chat(messages, **kw):
        eid = _evidence_id(messages[-1]["content"], "120.7 billion")
        llm._scripts = [f"It was ETB 120.7 billion [{eid}].\nFOLLOW-UPS:\n- Why?"]
        return original(messages, **kw)

    llm._chat = chat
    pieces: list[str] = []
    answer = agent.ask("What was import tax expenditure in FY 2020/21?", on_token=pieces.append)
    shown = "".join(pieces)
    assert shown.strip() == "It was ETB 120.7 billion [Page 4]."
    assert "FOLLOW" not in shown
    assert answer.timings["first_token_s"] <= answer.timings["total_s"]


def test_stream_filter_handles_ids_and_trailer_split_across_pieces():
    f = StreamFilter({1: "[Page 3]", 2: "[Page 9]"})
    out = "".join(f.feed(p) for p in ["Revenue rose [", "E1", "][E2]. Next\nFOLL", "OW-UPS:\n- a"]) + f.finish()
    assert out == "Revenue rose [Page 3][Page 9]. Next"


def test_split_follow_ups_and_display_text():
    body, ups = split_follow_ups("Answer [E1].\n\nFOLLOW-UPS:\n- One?\n- Two?\n- Three?")
    assert body == "Answer [E1]." and ups == ["One?", "Two?"]
    assert display_text("A [E1][E2] B [E2].", {1: "[Page 4]", 2: "[Page 4]"}) == "A [Page 4] B [Page 4]."


def test_rules_plan_reads_change_questions():
    plan = rules_plan("By what percentage did total revenue change from 2022/23 to 2023/24?")
    assert plan.facts["op"] == "percent_change" and plan.facts["periods"] == ["2022/23", "2023/24"]
    assert "revenue" in plan.facts["metric"].lower()
    plan = rules_plan("According to the EthSwitch Annual Report 2023/2024, what is the figure for “PIN Issuance Fee” for 2023/24?")
    assert plan.facts["metric"] == "PIN Issuance Fee"
    assert rules_plan("thanks!").kind == "chitchat"


def test_greeting_without_document():
    llm = _ScriptedLLM([])
    answer = _agent(llm, doc_id=None, stores=memory_stores()).ask("Hello!")
    assert "welcome to docmind" in answer.answer.lower()
    assert answer.provenance.is_empty and answer.status == "greeting"
    assert llm.calls == []


def test_greeting_with_document():
    llm = _ScriptedLLM([])
    answer = _agent(llm, doc_id="annual_report", stores=memory_stores()).ask("Hi!")
    assert "ready to help" in answer.answer.lower()
    assert llm.calls == []


def test_a_stream_that_stops_partway_is_asked_again_without_streaming():
    llm = _ScriptedLLM([])
    agent = _agent(llm)
    original = llm._chat
    streams: list[int] = []

    def chat(messages, **kw):
        eid = _evidence_id(messages[-1]["content"], "120.7 billion")
        llm._scripts = [f"It was ETB 120.7 billion [{eid}]."]
        return original(messages, **kw)

    def stream(messages, **kw):
        streams.append(1)
        yield "It was ETB "
        raise LLMError("ReadTimeout while streaming", kind="timeout", provider="fake")

    llm._chat = chat
    llm._stream = stream
    pieces: list[str] = []
    answer = agent.ask("What was import tax expenditure in FY 2020/21?", on_token=pieces.append)
    assert streams == [1]
    assert answer.status == "answered" and "120.7 billion" in answer.answer
    assert answer.provenance.citations[0].page_number == 4
