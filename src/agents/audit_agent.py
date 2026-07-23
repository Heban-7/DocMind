"""
Audit Mode agent (Phase 4 Step 8).

Analogy: a skeptical fact-checker. Given a claim, it gathers evidence with the
same three tools as the Query Agent, then either stamps VERIFIED + citations
or UNVERIFIABLE. It never silently agrees.

Cost-conscious default: heuristic tool plan (no planner LLM) + one judge LLM
call. Set use_planner=True to mirror the Query Agent's planner.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.audit_prompts import AUDITOR_SYSTEM, auditor_user_prompt
from src.agents.query_agent import (
    QueryAgentDeps,
    _default_plan,
    _extract_json,
    _format_hit,
    _run_one_tool,
)
from src.agents.query_prompts import PLANNER_SYSTEM, planner_user_prompt
from src.config import DEFAULT_SAMPLE_PDF
from src.facts.store import FactStore
from src.llm.base import LLMClient
from src.llm.factory import get_text_client
from src.models.provenance import ProvenanceChain
from src.models.query import AuditStatus, AuditVerdict, ToolName, ToolTrace
from src.query.evidence import EvidenceHit, ToolResult
from src.query.provenance import assemble_provenance
from src.retrieval.embeddings import EmbeddingClient
from src.retrieval.vector_store import ChromaLDUStore

logger = logging.getLogger("docmind.audit_agent")


class AuditState(TypedDict, total=False):
    claim: str
    doc_id: str
    pdf_path: str | None
    plan_calls: list[dict[str, Any]]
    hits: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    status: str
    rationale: str
    cite_indices: list[int]
    verdict: dict[str, Any] | None
    error: str | None


@dataclass
class AuditAgentDeps(QueryAgentDeps):
    """Same injectable stores as QueryAgent, plus optional LLM planner."""

    use_planner: bool = False


def _normalize_calls(
    calls: list[Any],
    *,
    max_tool_calls: int,
    fallback_text: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in calls[:max_tool_calls]:
        if not isinstance(raw, dict):
            continue
        tool = str(raw.get("tool") or "").strip()
        if not tool:
            continue
        normalized.append({"tool": tool, "args": dict(raw.get("args") or {})})
    if not normalized:
        normalized = _default_plan(fallback_text)[:max_tool_calls]
    return normalized


@dataclass
class AuditAgent:
    """LangGraph runner: plan tools -> gather evidence -> judge claim."""

    deps: AuditAgentDeps
    _graph: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._graph = self._build_graph()

    def _build_graph(self):
        deps = self.deps

        def plan_node(state: AuditState) -> AuditState:
            claim = state["claim"]
            if not deps.use_planner:
                return {
                    "plan_calls": _normalize_calls(
                        _default_plan(claim),
                        max_tool_calls=deps.max_tool_calls,
                        fallback_text=claim,
                    ),
                    "error": None,
                }
            try:
                result = deps.llm.complete(
                    planner_user_prompt(claim, deps.doc_id),
                    system=PLANNER_SYSTEM,
                    response_format="json",
                    temperature=0.0,
                    max_tokens=400,
                )
                payload = _extract_json(result.text)
                calls = payload.get("calls")
                if not isinstance(calls, list) or not calls:
                    calls = _default_plan(claim)
            except Exception as exc:  # pragma: no cover
                logger.warning("Audit planner failed (%s); heuristic plan", exc)
                calls = _default_plan(claim)
            return {
                "plan_calls": _normalize_calls(
                    calls,
                    max_tool_calls=deps.max_tool_calls,
                    fallback_text=claim,
                ),
                "error": None,
            }

        def tools_node(state: AuditState) -> AuditState:
            hits: list[EvidenceHit] = []
            traces: list[ToolTrace] = []
            for call in state.get("plan_calls") or []:
                try:
                    result = _run_one_tool(
                        call, deps, active_doc_id=deps.doc_id
                    )
                except Exception as exc:
                    name = str(call.get("tool") or ToolName.SEMANTIC_SEARCH.value)
                    try:
                        tool_name = ToolName(name)
                    except ValueError:
                        tool_name = ToolName.SEMANTIC_SEARCH
                    logger.warning("Audit tool %s failed: %s", name, exc)
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
            from src.query.page_map import enrich_hit_printed_page

            hits = [
                enrich_hit_printed_page(h, pdf_path=deps.pdf_path) for h in hits
            ]
            return {
                "hits": [h.model_dump(mode="json") for h in hits],
                "tool_trace": [t.model_dump(mode="json") for t in traces],
            }

        def judge_node(state: AuditState) -> AuditState:
            hits = [EvidenceHit.model_validate(h) for h in (state.get("hits") or [])]
            claim = state["claim"]

            # Fast path: nothing retrieved -> unverifiable, skip LLM.
            if not hits:
                return {
                    "status": AuditStatus.UNVERIFIABLE.value,
                    "rationale": "No supporting evidence was retrieved for this claim.",
                    "cite_indices": [],
                }

            blocks = [_format_hit(h, i) for i, h in enumerate(hits)]
            try:
                result = deps.llm.complete(
                    auditor_user_prompt(claim, blocks),
                    system=AUDITOR_SYSTEM,
                    response_format="json",
                    temperature=0.0,
                    max_tokens=400,
                )
                payload = _extract_json(result.text)
            except Exception as exc:  # pragma: no cover
                logger.warning("Auditor LLM failed (%s)", exc)
                payload = {}

            status_raw = str(payload.get("status") or "").strip().lower()
            if status_raw not in {
                AuditStatus.VERIFIED.value,
                AuditStatus.UNVERIFIABLE.value,
            }:
                status_raw = AuditStatus.UNVERIFIABLE.value

            rationale = str(payload.get("rationale") or "").strip()
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

            # Honest gate: verified without cites is illegal -> force unverifiable.
            if status_raw == AuditStatus.VERIFIED.value and not cite_indices:
                status_raw = AuditStatus.UNVERIFIABLE.value
                rationale = (
                    rationale
                    or "Model marked verified but provided no citations; treating as unverifiable."
                )
                cite_indices = []

            if not rationale:
                rationale = (
                    "Evidence supports the claim."
                    if status_raw == AuditStatus.VERIFIED.value
                    else "Could not verify the claim against retrieved evidence."
                )

            return {
                "status": status_raw,
                "rationale": rationale,
                "cite_indices": cite_indices,
            }

        def finalize_node(state: AuditState) -> AuditState:
            hits = [EvidenceHit.model_validate(h) for h in (state.get("hits") or [])]
            status = AuditStatus(state.get("status") or AuditStatus.UNVERIFIABLE.value)
            idxs = state.get("cite_indices") or []
            selected = [hits[i] for i in idxs if 0 <= i < len(hits)]

            if status is AuditStatus.VERIFIED:
                provenance = assemble_provenance(
                    selected, pdf_path=deps.pdf_path, max_citations=8
                )
                if provenance.is_empty:
                    # Cannot honestly verify without citations.
                    status = AuditStatus.UNVERIFIABLE
                    rationale = (
                        (state.get("rationale") or "")
                        + " Provenance assembly produced no usable citations."
                    ).strip()
                    provenance = ProvenanceChain()
                else:
                    rationale = state.get("rationale") or "Evidence supports the claim."
            else:
                provenance = ProvenanceChain()
                rationale = (
                    state.get("rationale")
                    or "Could not verify the claim against retrieved evidence."
                )

            traces = [
                ToolTrace.model_validate(t) for t in (state.get("tool_trace") or [])
            ]
            verdict = AuditVerdict(
                claim=state["claim"],
                status=status,
                provenance=provenance,
                rationale=rationale,
                doc_id=deps.doc_id,
                tool_trace=traces,
            )
            return {"verdict": verdict.model_dump(mode="json")}

        graph = StateGraph(AuditState)
        graph.add_node("plan", plan_node)
        graph.add_node("execute_tools", tools_node)
        graph.add_node("judge", judge_node)
        graph.add_node("finalize", finalize_node)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "execute_tools")
        graph.add_edge("execute_tools", "judge")
        graph.add_edge("judge", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def audit(self, claim: str) -> AuditVerdict:
        """Check a claim; return verified+citations or unverifiable."""
        from src.observability.langsmith import tracing_enabled

        claim = (claim or "").strip()
        if not claim:
            return AuditVerdict(
                claim="",
                status=AuditStatus.UNVERIFIABLE,
                rationale="Empty claim cannot be verified.",
                doc_id=self.deps.doc_id,
            )

        def _invoke() -> AuditVerdict:
            final = self._graph.invoke(
                {
                    "claim": claim,
                    "doc_id": self.deps.doc_id,
                    "pdf_path": str(self.deps.pdf_path) if self.deps.pdf_path else None,
                    "plan_calls": [],
                    "hits": [],
                    "tool_trace": [],
                    "status": AuditStatus.UNVERIFIABLE.value,
                    "rationale": "",
                    "cite_indices": [],
                    "verdict": None,
                    "error": None,
                }
            )
            return AuditVerdict.model_validate(final.get("verdict") or {})

        if not tracing_enabled():
            return _invoke()
        try:
            from langsmith import trace
        except Exception:  # pragma: no cover
            return _invoke()

        with trace(
            name="docmind.audit.audit",
            run_type="chain",
            inputs={"claim": claim, "doc_id": self.deps.doc_id},
            tags=["docmind", "audit"],
            metadata={"agent": "AuditAgent"},
        ) as run:
            verdict = _invoke()
            try:
                run.end(
                    outputs={
                        "status": verdict.status.value,
                        "citations": len(verdict.provenance),
                        "rationale": verdict.rationale,
                    }
                )
            except Exception:  # pragma: no cover
                pass
            return verdict


def build_audit_agent(
    doc_id: str,
    *,
    llm: LLMClient | None = None,
    pdf_path: str | Path | None = None,
    pageindex_dir: Path | None = None,
    chroma_store: ChromaLDUStore | None = None,
    embedder: EmbeddingClient | None = None,
    fact_store: FactStore | None = None,
    max_tool_calls: int = 3,
    use_planner: bool = False,
) -> AuditAgent:
    """Factory: uses ``get_text_client()`` when ``llm`` is omitted."""
    client = llm if llm is not None else get_text_client()
    if client is None:
        raise RuntimeError(
            "No LLM client available. Set OPENAI_API_KEY (or another provider "
            "key) in .env, or pass llm= explicitly."
        )
    return AuditAgent(
        AuditAgentDeps(
            llm=client,
            doc_id=doc_id,
            pdf_path=pdf_path or DEFAULT_SAMPLE_PDF,
            pageindex_dir=pageindex_dir,
            chroma_store=chroma_store,
            embedder=embedder,
            fact_store=fact_store,
            max_tool_calls=max_tool_calls,
            use_planner=use_planner,
        )
    )
