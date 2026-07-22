"""
LangGraph Query Agent (Phase 4 Step 7).

Analogy: a research supervisor who (1) decides which assistants to send,
(2) collects their sticky notes, (3) writes a short answer with footnotes.

Graph (one pass, cost-conscious):
    plan  ?  execute_tools  ?  synthesize  ?  finalize  ?  END

Uses DocMind's existing ``LLMClient`` (not a separate LangChain chat model),
so provider/key wiring stays identical to the rest of the refinery.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

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
from src.models.provenance import ProvenanceChain
from src.models.query import QueryAnswer, ToolName, ToolTrace
from src.query.evidence import EvidenceHit, ToolResult
from src.query.provenance import assemble_provenance
from src.query.tools import pageindex_navigate, semantic_search, structured_query
from src.retrieval.embeddings import EmbeddingClient
from src.retrieval.vector_store import ChromaLDUStore

logger = logging.getLogger("docmind.query_agent")

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


class QueryState(TypedDict, total=False):
    question: str
    doc_id: str
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
    doc_id: str
    pdf_path: str | Path | None = None
    pageindex_dir: Path | None = None
    chroma_store: ChromaLDUStore | None = None
    embedder: EmbeddingClient | None = None
    fact_store: FactStore | None = None
    max_tool_calls: int = 3
    semantic_top_k: int = 5
    pageindex_top_k: int = 3


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT_RE.search(text)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _default_plan(question: str) -> list[dict[str, Any]]:
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
        # Pull a coarse metric keyword (first 4 content words).
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
        f"page={hit.page_number}",
        f"title={hit.title!r}" if hit.title else None,
        f"excerpt={hit.excerpt!r}",
    ]
    return " | ".join(b for b in bits if b)


def _run_one_tool(
    call: dict[str, Any],
    deps: QueryAgentDeps,
) -> ToolResult:
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
        return pageindex_navigate(
            str(args.get("topic") or deps.doc_id),
            doc_id=deps.doc_id,
            top_k=int(args.get("top_k") or deps.pageindex_top_k),
            pageindex_dir=deps.pageindex_dir or PAGEINDEX_DIR,
        )
    if tool is ToolName.SEMANTIC_SEARCH:
        return semantic_search(
            str(args.get("query") or ""),
            doc_id=deps.doc_id,
            top_k=int(args.get("top_k") or deps.semantic_top_k),
            store=deps.chroma_store,
            embedder=deps.embedder,
        )
    # structured_query
    return structured_query(
        doc_id=deps.doc_id,
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

        def plan_node(state: QueryState) -> QueryState:
            question = state["question"]
            try:
                result = deps.llm.complete(
                    planner_user_prompt(question, deps.doc_id),
                    system=PLANNER_SYSTEM,
                    response_format="json",
                    temperature=0.0,
                    max_tokens=400,
                )
                payload = _extract_json(result.text)
                calls = payload.get("calls")
                if not isinstance(calls, list) or not calls:
                    calls = _default_plan(question)
            except Exception as exc:  # pragma: no cover - network / provider
                logger.warning("Planner failed (%s); using heuristic plan", exc)
                calls = _default_plan(question)

            # Cap cost: hard limit on tool fan-out.
            normalized: list[dict[str, Any]] = []
            for raw in calls[: deps.max_tool_calls]:
                if not isinstance(raw, dict):
                    continue
                tool = str(raw.get("tool") or "").strip()
                if not tool:
                    continue
                normalized.append(
                    {"tool": tool, "args": dict(raw.get("args") or {})}
                )
            if not normalized:
                normalized = _default_plan(question)[: deps.max_tool_calls]
            return {"plan_calls": normalized, "error": None}

        def tools_node(state: QueryState) -> QueryState:
            hits: list[EvidenceHit] = []
            traces: list[ToolTrace] = []
            for call in state.get("plan_calls") or []:
                try:
                    result = _run_one_tool(call, deps)
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
            try:
                result = deps.llm.complete(
                    synthesizer_user_prompt(question, blocks),
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
                # Force citations when the model forgot: use top evidence.
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
                provenance = assemble_provenance(
                    selected,
                    pdf_path=deps.pdf_path,
                    max_citations=8,
                )
                # If assembly skipped empty excerpts, fall back to all selected
                # with any text so QueryAnswer validation can pass.
                if provenance.is_empty and selected:
                    provenance = assemble_provenance(
                        [h for h in selected if h.excerpt or h.content_hash],
                        pdf_path=deps.pdf_path,
                    )

            traces = [
                ToolTrace.model_validate(t) for t in (state.get("tool_trace") or [])
            ]
            answer_text = state.get("draft_answer") or (
                "I could not find that in the document."
            )
            # Guarantee validator-safe refusal wording when we have no cites.
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
                doc_id=deps.doc_id,
            )
            return {"answer": qa.model_dump(mode="json")}

        graph = StateGraph(QueryState)
        graph.add_node("plan", plan_node)
        graph.add_node("execute_tools", tools_node)
        graph.add_node("synthesize", synthesize_node)
        graph.add_node("finalize", finalize_node)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "execute_tools")
        graph.add_edge("execute_tools", "synthesize")
        graph.add_edge("synthesize", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def ask(self, question: str) -> QueryAnswer:
        """Run the graph and return a typed QueryAnswer."""
        question = (question or "").strip()
        if not question:
            return QueryAnswer(
                question="",
                answer="I could not find that in the document.",
                provenance=ProvenanceChain(),
                doc_id=self.deps.doc_id,
            )
        final = self._graph.invoke(
            {
                "question": question,
                "doc_id": self.deps.doc_id,
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
        )
        payload = final.get("answer") or {}
        return QueryAnswer.model_validate(payload)


def build_query_agent(
    doc_id: str,
    *,
    llm: LLMClient | None = None,
    pdf_path: str | Path | None = None,
    pageindex_dir: Path | None = None,
    chroma_store: ChromaLDUStore | None = None,
    embedder: EmbeddingClient | None = None,
    fact_store: FactStore | None = None,
    max_tool_calls: int = 3,
) -> QueryAgent:
    """Factory: uses ``get_text_client()`` when ``llm`` is omitted."""
    client = llm if llm is not None else get_text_client()
    if client is None:
        raise RuntimeError(
            "No LLM client available. Set OPENAI_API_KEY (or another provider "
            "key) in .env, or pass llm= explicitly."
        )
    return QueryAgent(
        QueryAgentDeps(
            llm=client,
            doc_id=doc_id,
            pdf_path=pdf_path or DEFAULT_SAMPLE_PDF,
            pageindex_dir=pageindex_dir,
            chroma_store=chroma_store,
            embedder=embedder,
            fact_store=fact_store,
            max_tool_calls=max_tool_calls,
        )
    )
