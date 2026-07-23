"""
LangGraph Query Agent (Phase 4).

Analogy: a research supervisor who (1) decides which assistants to send,
(2) collects their sticky notes, (3) writes a short answer with footnotes.

Graph (one pass, cost-conscious):
    plan -> execute_tools -> synthesize -> finalize -> END

STEP 1 adds a Patient File: conversation ``messages`` persisted via a LangGraph
SqliteSaver checkpointer keyed by ``thread_id``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from src.agents.intent_router import list_corpus_documents, route_intent
from src.agents.json_util import extract_json
from src.agents.query_prompts import (
    PLANNER_SYSTEM,
    SYNTHESIZER_SYSTEM,
    planner_user_prompt,
    synthesizer_user_prompt,
)
from src.config import DEFAULT_SAMPLE_PDF, PAGEINDEX_DIR
from src.facts.store import FactStore
from src.llm.base import LLMClient
from src.llm.factory import get_text_client
from src.models.conversation import ConversationMessage, MessageRole, SessionConfig
from src.models.intent import CorpusDocument, IntentRouter
from src.models.provenance import ProvenanceChain
from src.models.query import QueryAnswer, ToolName, ToolTrace
from src.pipeline.phase4 import resolve_pdf_path
from src.query.evidence import EvidenceHit, ToolResult
from src.query.provenance import assemble_provenance
from src.query.tools import pageindex_navigate, semantic_search, structured_query
from src.retrieval.embeddings import EmbeddingClient
from src.retrieval.vector_store import ChromaLDUStore

logger = logging.getLogger("docmind.query_agent")


class QueryState(TypedDict, total=False):
    """LangGraph state. ``messages`` accumulate across turns when checkpointed."""

    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    doc_id: str
    active_doc_id: str | None
    intent: dict[str, Any]
    pdf_path: str | None
    plan_calls: list[dict[str, Any]]
    hits: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    draft_answer: str
    cite_indices: list[int]
    refusal: bool
    answer: dict[str, Any] | None
    error: str | None


@dataclass
class QueryAgentDeps:
    """Injectable stores / clients so unit tests stay offline and free."""

    llm: LLMClient
    doc_id: str | None = None  # forced pin; None => IntentRouter decides
    pdf_path: str | Path | None = None
    pageindex_dir: Path | None = None
    chroma_store: ChromaLDUStore | None = None
    embedder: EmbeddingClient | None = None
    fact_store: FactStore | None = None
    checkpointer: BaseCheckpointSaver | None = None
    corpus: list[CorpusDocument] | None = None
    max_tool_calls: int = 3
    semantic_top_k: int = 5
    pageindex_top_k: int = 3
    history_max_messages: int = 12


def _extract_json(text: str) -> dict[str, Any]:
    """Backward-compatible alias."""
    return extract_json(text)

def _default_plan(
    question: str,
    *,
    allow_pageindex: bool = True,
) -> list[dict[str, Any]]:
    """Cheap heuristic plan used when the LLM returns unusable JSON."""
    q = question.strip()
    calls: list[dict[str, Any]] = [
        {"tool": ToolName.SEMANTIC_SEARCH.value, "args": {"query": q, "top_k": 5}},
    ]
    lowered = q.lower()
    if any(
        w in lowered
        for w in (
            "how much", "what was", "revenue", "expenditure", "etb", "$",
            "billion", "million", "percent", "%", "fy ", "20",
        )
    ):
        tokens = [t for t in re.findall(r"[A-Za-z]{3,}", q) if t.lower() not in {
            "what", "was", "were", "how", "much", "many", "the", "and", "for",
            "in", "of", "to", "a", "an",
        }]
        metric = " ".join(tokens[:3]) if tokens else None
        calls.append(
            {
                "tool": ToolName.STRUCTURED_QUERY.value,
                "args": {"metric_contains": metric, "limit": 10},
            }
        )
    if allow_pageindex:
        calls.append(
            {
                "tool": ToolName.PAGEINDEX_NAVIGATE.value,
                "args": {"topic": q, "top_k": 3},
            }
        )
    return calls[:3]


def _format_hit(hit: EvidenceHit, index: int) -> str:
    bits = [
        f"tool={hit.tool.value}",
        f"doc={hit.doc_id}" if hit.doc_id else None,
        f"page={hit.page_number}",
        f"title={hit.title!r}" if hit.title else None,
        f"excerpt={hit.excerpt!r}",
    ]
    return " | ".join(b for b in bits if b)


def _format_history(messages: list[BaseMessage], *, max_messages: int) -> str:
    """Render prior turns for planner/synthesizer (excludes the latest human)."""
    if not messages:
        return ""
    prior = list(messages[:-1]) if messages else []
    window = prior[-max_messages:] if max_messages > 0 else prior
    lines: list[str] = []
    for msg in window:
        role = getattr(msg, "type", "unknown")
        content = str(getattr(msg, "content", "") or "").strip()
        if not content:
            continue
        if len(content) > 400:
            content = content[:400] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _run_one_tool(
    call: dict[str, Any],
    deps: QueryAgentDeps,
    *,
    active_doc_id: str | None,
) -> ToolResult:
    """Run one retrieval tool, applying the IntentRouter's doc filter."""
    name = str(call.get("tool") or "").strip()
    args = dict(call.get("args") or {})
    try:
        tool = ToolName(name)
    except ValueError:
        return ToolResult(
            tool=ToolName.SEMANTIC_SEARCH,
            hits=[],
            trace=ToolTrace(
                tool=ToolName.SEMANTIC_SEARCH,
                arguments=args,
                summary=f"unknown tool '{name}' skipped",
            ),
        )

    if tool is ToolName.PAGEINDEX_NAVIGATE:
        if not active_doc_id:
            return ToolResult(
                tool=tool,
                hits=[],
                trace=ToolTrace(
                    tool=tool,
                    arguments=args,
                    summary="skipped: pageindex requires a scoped document_id",
                ),
            )
        return pageindex_navigate(
            str(args.get("topic") or active_doc_id),
            doc_id=active_doc_id,
            top_k=int(args.get("top_k") or deps.pageindex_top_k),
            pageindex_dir=deps.pageindex_dir or PAGEINDEX_DIR,
        )
    if tool is ToolName.SEMANTIC_SEARCH:
        # IntentRouter output: concrete id => Chroma metadata filter;
        # None => federated corpus search.
        return semantic_search(
            str(args.get("query") or ""),
            doc_id=active_doc_id,
            top_k=int(args.get("top_k") or deps.semantic_top_k),
            store=deps.chroma_store,
            embedder=deps.embedder,
        )
    return structured_query(
        doc_id=active_doc_id,
        metric_contains=args.get("metric_contains"),
        period_contains=args.get("period_contains"),
        sql=args.get("sql"),
        limit=int(args.get("limit") or 20),
        store=deps.fact_store,
    )


@dataclass
class QueryAgent:
    """Compile-once LangGraph runner scoped to a single document."""

    deps: QueryAgentDeps
    _graph: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._graph = self._build_graph()

    def _build_graph(self):
        deps = self.deps

        def route_node(state: QueryState) -> QueryState:
            """IntentRouter before retrieval: pin one doc or search the corpus."""
            question = state["question"]
            corpus = deps.corpus
            if corpus is None:
                corpus = list_corpus_documents()
            intent = route_intent(
                question,
                corpus=corpus,
                llm=None if deps.doc_id else deps.llm,
                forced_document_id=deps.doc_id,
            )
            active = intent.document_id
            pdf = deps.pdf_path
            if active and pdf is None:
                pdf = resolve_pdf_path(active)
            return {
                "intent": intent.model_dump(mode="json"),
                "active_doc_id": active,
                "doc_id": active or "",
                "pdf_path": str(pdf) if pdf else None,
                "error": None,
            }

        def plan_node(state: QueryState) -> QueryState:
            question = state["question"]
            active = state.get("active_doc_id")
            allow_pageindex = bool(active)
            history = _format_history(
                list(state.get("messages") or []),
                max_messages=deps.history_max_messages,
            )
            scope_label = active or "CORPUS (all documents)"
            try:
                result = deps.llm.complete(
                    planner_user_prompt(
                        question,
                        scope_label,
                        history=history,
                    ),
                    system=PLANNER_SYSTEM,
                    response_format="json",
                    temperature=0.0,
                    max_tokens=400,
                )
                payload = _extract_json(result.text)
                calls = payload.get("calls")
                if not isinstance(calls, list) or not calls:
                    calls = _default_plan(question, allow_pageindex=allow_pageindex)
            except Exception as exc:  # pragma: no cover - network / provider
                logger.warning("Planner failed (%s); using heuristic plan", exc)
                calls = _default_plan(question, allow_pageindex=allow_pageindex)

            normalized: list[dict[str, Any]] = []
            for raw in calls[: deps.max_tool_calls]:
                if not isinstance(raw, dict):
                    continue
                tool = str(raw.get("tool") or "").strip()
                if not tool:
                    continue
                # Corpus-wide: drop pageindex even if planner asked for it.
                if tool == ToolName.PAGEINDEX_NAVIGATE.value and not allow_pageindex:
                    continue
                normalized.append(
                    {"tool": tool, "args": dict(raw.get("args") or {})}
                )
            if not normalized:
                normalized = _default_plan(
                    question, allow_pageindex=allow_pageindex
                )[: deps.max_tool_calls]
            return {"plan_calls": normalized, "error": None}

        def tools_node(state: QueryState) -> QueryState:
            hits: list[EvidenceHit] = []
            traces: list[ToolTrace] = []
            active = state.get("active_doc_id")
            for call in state.get("plan_calls") or []:
                try:
                    result = _run_one_tool(call, deps, active_doc_id=active)
                except Exception as exc:
                    name = str(call.get("tool") or ToolName.SEMANTIC_SEARCH.value)
                    try:
                        tool_name = ToolName(name)
                    except ValueError:
                        tool_name = ToolName.SEMANTIC_SEARCH
                    logger.warning("Tool %s failed: %s", name, exc)
                    result = ToolResult(
                        tool=tool_name,
                        hits=[],
                        trace=ToolTrace(
                            tool=tool_name,
                            arguments=dict(call.get("args") or {}),
                            summary=f"tool error: {exc}",
                        ),
                    )
                hits.extend(result.hits)
                traces.append(result.trace)
            return {
                "hits": [h.model_dump(mode="json") for h in hits],
                "tool_trace": [t.model_dump(mode="json") for t in traces],
            }

        def synthesize_node(state: QueryState) -> QueryState:
            hits = [EvidenceHit.model_validate(h) for h in (state.get("hits") or [])]
            blocks = [_format_hit(h, i) for i, h in enumerate(hits)]
            question = state["question"]
            history = _format_history(
                list(state.get("messages") or []),
                max_messages=deps.history_max_messages,
            )
            try:
                result = deps.llm.complete(
                    synthesizer_user_prompt(question, blocks, history=history),
                    system=SYNTHESIZER_SYSTEM,
                    response_format="json",
                    temperature=0.0,
                    max_tokens=500,
                )
                payload = _extract_json(result.text)
            except Exception as exc:  # pragma: no cover
                logger.warning("Synthesizer failed (%s)", exc)
                payload = {}

            refusal = bool(payload.get("refusal"))
            answer = str(payload.get("answer") or "").strip()
            raw_idxs = payload.get("cite_indices") or []
            cite_indices: list[int] = []
            if isinstance(raw_idxs, list):
                for x in raw_idxs:
                    try:
                        i = int(x)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= i < len(hits):
                        cite_indices.append(i)

            if not answer:
                refusal = True
                answer = "I could not find that in the document."
                cite_indices = []
            elif not hits:
                refusal = True
                if "could not find" not in answer.lower():
                    answer = "I could not find that in the document."
                cite_indices = []
            elif not refusal and not cite_indices:
                cite_indices = list(range(min(3, len(hits))))

            return {
                "draft_answer": answer,
                "cite_indices": cite_indices,
                "refusal": refusal,
            }

        def finalize_node(state: QueryState) -> QueryState:
            hits = [EvidenceHit.model_validate(h) for h in (state.get("hits") or [])]
            idxs = state.get("cite_indices") or []
            selected = [hits[i] for i in idxs if 0 <= i < len(hits)]
            if state.get("refusal") or not selected:
                provenance = ProvenanceChain()
            else:
                pdf_for_cite = state.get("pdf_path") or deps.pdf_path
                if not pdf_for_cite and selected and selected[0].doc_id:
                    pdf_for_cite = resolve_pdf_path(selected[0].doc_id)
                provenance = assemble_provenance(
                    selected,
                    pdf_path=pdf_for_cite,
                    max_citations=8,
                )
                if provenance.is_empty and selected:
                    provenance = assemble_provenance(
                        [h for h in selected if h.excerpt or h.content_hash],
                        pdf_path=pdf_for_cite,
                    )

            traces = [
                ToolTrace.model_validate(t) for t in (state.get("tool_trace") or [])
            ]
            answer_text = state.get("draft_answer") or (
                "I could not find that in the document."
            )
            if provenance.is_empty:
                lowered = answer_text.lower()
                if not any(
                    m in lowered
                    for m in (
                        "could not find",
                        "not found",
                        "unverifiable",
                        "no supporting",
                        "i don't know",
                        "i do not know",
                    )
                ):
                    answer_text = "I could not find that in the document."

            qa = QueryAnswer(
                question=state["question"],
                answer=answer_text,
                provenance=provenance,
                tool_trace=traces,
                doc_id=state.get("active_doc_id") or deps.doc_id,
            )
            # Persist assistant turn onto the Patient File (messages channel).
            return {
                "answer": qa.model_dump(mode="json"),
                "messages": [AIMessage(content=answer_text)],
            }

        graph = StateGraph(QueryState)
        graph.add_node("route", route_node)
        graph.add_node("plan", plan_node)
        graph.add_node("execute_tools", tools_node)
        graph.add_node("synthesize", synthesize_node)
        graph.add_node("finalize", finalize_node)
        graph.set_entry_point("route")
        graph.add_edge("route", "plan")
        graph.add_edge("plan", "execute_tools")
        graph.add_edge("execute_tools", "synthesize")
        graph.add_edge("synthesize", "finalize")
        graph.add_edge("finalize", END)
        if deps.checkpointer is not None:
            return graph.compile(checkpointer=deps.checkpointer)
        return graph.compile()

    def ask(
        self,
        question: str,
        *,
        thread_id: str | None = None,
    ) -> QueryAnswer:
        """Run the graph and return a typed QueryAnswer.

        Pass the same ``thread_id`` on later calls to resume conversation memory
        (requires a checkpointer on ``QueryAgentDeps``).
        """
        question = (question or "").strip()
        if not question:
            return QueryAnswer(
                question="",
                answer="I could not find that in the document.",
                provenance=ProvenanceChain(),
                doc_id=self.deps.doc_id,
            )

        payload_in: dict[str, Any] = {
            "messages": [HumanMessage(content=question)],
            "question": question,
            "doc_id": self.deps.doc_id or "",
            "active_doc_id": self.deps.doc_id,
            "intent": {},
            "pdf_path": str(self.deps.pdf_path) if self.deps.pdf_path else None,
            "plan_calls": [],
            "hits": [],
            "tool_trace": [],
            "draft_answer": "",
            "cite_indices": [],
            "refusal": False,
            "answer": None,
            "error": None,
        }

        if self.deps.checkpointer is not None:
            tid = (thread_id or "default").strip() or "default"
            config = SessionConfig(thread_id=tid).to_runnable_config()
            final = self._graph.invoke(payload_in, config=config)
        else:
            final = self._graph.invoke(payload_in)

        payload = final.get("answer") or {}
        return QueryAnswer.model_validate(payload)

    def get_messages(
        self,
        thread_id: str,
    ) -> list[ConversationMessage]:
        """Read persisted turns for a thread (empty if no checkpointer)."""
        if self.deps.checkpointer is None:
            return []
        config = SessionConfig(thread_id=thread_id).to_runnable_config()
        snap = self._graph.get_state(config)
        values = snap.values if snap else {}
        raw = list(values.get("messages") or [])
        out: list[ConversationMessage] = []
        for msg in raw:
            content = str(getattr(msg, "content", "") or "").strip()
            if not content:
                continue
            mtype = getattr(msg, "type", "")
            if mtype == "human":
                role = MessageRole.USER
            elif mtype == "ai":
                role = MessageRole.ASSISTANT
            else:
                role = MessageRole.SYSTEM
            out.append(ConversationMessage(role=role, content=content))
        return out


def build_query_agent(
    doc_id: str | None = None,
    *,
    llm: LLMClient | None = None,
    pdf_path: str | Path | None = None,
    pageindex_dir: Path | None = None,
    chroma_store: ChromaLDUStore | None = None,
    embedder: EmbeddingClient | None = None,
    fact_store: FactStore | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    enable_memory: bool = False,
    checkpoints_db: str | Path | None = None,
    corpus: list[CorpusDocument] | None = None,
    max_tool_calls: int = 3,
) -> QueryAgent:
    """Factory: uses ``get_text_client()`` when ``llm`` is omitted.

    Pass ``doc_id`` to pin one document. Omit it to let IntentRouter choose
    single-doc vs corpus-wide search.

    Set ``enable_memory=True`` (or pass ``checkpointer=``) to persist sessions
    under ``.refinery/checkpoints.sqlite`` (override with ``checkpoints_db``).
    """
    from src.agents.memory import build_sqlite_checkpointer

    client = llm if llm is not None else get_text_client()
    if client is None:
        raise RuntimeError(
            "No LLM client available. Set OPENAI_API_KEY (or another provider "
            "key) in .env, or pass llm= explicitly."
        )
    saver = checkpointer
    if saver is None and enable_memory:
        saver = build_sqlite_checkpointer(checkpoints_db)

    return QueryAgent(
        QueryAgentDeps(
            llm=client,
            doc_id=doc_id,
            pdf_path=pdf_path if pdf_path is not None else (
                DEFAULT_SAMPLE_PDF if doc_id else None
            ),
            pageindex_dir=pageindex_dir,
            chroma_store=chroma_store,
            embedder=embedder,
            fact_store=fact_store,
            checkpointer=saver,
            corpus=corpus,
            max_tool_calls=max_tool_calls,
        )
    )
