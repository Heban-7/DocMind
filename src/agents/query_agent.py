"""
The answer engine (M7): plan, retrieve, answer (streamed), verify.

    understand ──> retrieve ──> answer ──> verify ──> END
        └──(greeting)────────────────────────────┘

* understand: a greeting is answered with no model call. Otherwise one model
  call plans (standalone question, document, fact lookup), or, for a first
  question about one document, a rule-based plan does, with no call at all.
  The search for the question starts at the same time as the planning call.
* retrieve: hybrid search, the fact lookup (arithmetic in SQL) and the
  section index run in parallel.
* answer: one model call writes the answer, citing evidence ids ([E2]); the
  text is streamed to the caller as it is written, with the ids shown as
  page badges.
* verify: every number is checked against the evidence it cites (see
  ``src.query.verify``); unsupported sentences are removed and citations
  point at the evidence that holds the numbers. No padding.

A failed model call raises ``LLMError``: the caller reports an error, never a
"not found" answer (audit P1-8). The whole answer shares one deadline.

Conversation memory (``messages``) is kept by a LangGraph checkpointer
(Postgres in the API) keyed by ``thread_id``.
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from src.agents.intent_router import _heuristic_route
from src.agents.json_util import extract_json
from src.agents.planning import GREETING, Plan, llm_plan, rules_plan
from src.agents.prompt_profiles import DEFAULT_MODE, PromptProfile, get_profile, normalize_mode
from src.llm import usage
from src.llm.base import LLMClient
from src.llm.errors import LLMError
from src.llm.factory import get_text_client
from src.models.conversation import ConversationMessage, MessageRole, SessionConfig
from src.models.intent import CorpusDocument
from src.models.provenance import ProvenanceChain
from src.models.query import QueryAnswer, ToolName, ToolTrace
from src.query.evidence import EvidenceHit, ToolResult
from src.query.provenance import assemble_provenance
from src.query.tools import pageindex_navigate, semantic_search, structured_query
from src.query.verify import CITE, NOT_FOUND, as_written, missing_scope_terms, verify_answer
from src.retrieval.embeddings import EmbeddingClient
from src.stores.base import Stores

logger = logging.getLogger("docmind.query_agent")

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="docmind-tools")
_TOKEN_SINK: contextvars.ContextVar[Callable[[str], None] | None] = contextvars.ContextVar("docmind_token_sink", default=None)
_RUN: contextvars.ContextVar[dict | None] = contextvars.ContextVar("docmind_answer_run", default=None)

# Kept for callers that imported it from here.
_GREETING_RE = GREETING

MAX_COMPUTED = 3
MAX_FACTS = 6
MAX_SECTIONS = 2


def _deadline_seconds() -> float:
    try:
        return float(os.getenv("DOCMIND_ANSWER_DEADLINE_S", "60"))
    except ValueError:
        return 60.0


class QueryState(TypedDict, total=False):
    """LangGraph state. ``messages`` accumulate across turns when checkpointed."""

    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    standalone: str
    mode: str
    doc_id: str
    active_doc_id: str | None
    pdf_path: str | None
    plan: dict[str, Any]
    # Evidence, traces and the draft live in the per-call run record, not here:
    # the checkpointer writes the state after every step, and the evidence of
    # one answer is tens of kilobytes.


def _resolve_pdf(deps: "QueryAgentDeps", doc_id: str | None) -> Path | None:
    if not doc_id or deps.pdf_resolver is None:
        return None
    try:
        return deps.pdf_resolver(doc_id)
    except Exception:  # a missing file only costs page labels and boxes
        return None


@dataclass
class QueryAgentDeps:
    """Injectable stores / clients so unit tests stay offline and free."""

    llm: LLMClient
    stores: Stores
    doc_id: str | None = None  # forced pin; None => the plan picks from the corpus
    pdf_path: str | Path | None = None
    # document id -> local PDF path (page labels and citation boxes)
    pdf_resolver: Callable[[str], Path | None] | None = None
    embedder: EmbeddingClient | None = None
    checkpointer: BaseCheckpointSaver | None = None
    corpus: list[CorpusDocument] = field(default_factory=list)
    max_tool_calls: int = 3  # kept for callers; the engine runs at most three tools
    semantic_top_k: int = 6
    pageindex_top_k: int = 3
    min_citations: int = 0  # unused since M7: citations are never padded
    max_citations: int = 8
    history_max_messages: int = 12
    planner: str = field(default_factory=lambda: os.getenv("DOCMIND_PLANNER", "auto"))  # auto | llm | rules
    profile: PromptProfile = field(default_factory=get_profile)
    mode: str = DEFAULT_MODE


def _extract_json(text: str) -> dict[str, Any]:
    """Backward-compatible alias."""
    return extract_json(text)


def _format_history(messages: list[BaseMessage], *, max_messages: int) -> str:
    """Render prior turns for the planner and the answer step (excludes the latest human)."""
    if not messages:
        return ""
    prior = list(messages[:-1])
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


# --- evidence ----------------------------------------------------------------


def _clip(n: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(n)))
    except (TypeError, ValueError):
        return default


def _search(deps: QueryAgentDeps, query: str, doc_id: str | None) -> ToolResult:
    return semantic_search(query, doc_id=doc_id, top_k=_clip(deps.semantic_top_k, 1, 10, 6), store=deps.stores.chunks, embedder=deps.embedder)


def _facts(deps: QueryAgentDeps, spec: dict, doc_id: str | None) -> ToolResult:
    spec = dict(spec)
    spec["limit"] = _clip(spec.get("limit", 10), 1, 20, 10)
    return structured_query(doc_id=doc_id, spec=spec, store=deps.stores.facts)


def _sections(deps: QueryAgentDeps, topic: str, doc_id: str) -> ToolResult:
    return pageindex_navigate(topic, doc_id=doc_id, top_k=_clip(deps.pageindex_top_k, 1, 5, 3), store=deps.stores.pageindex)


def _safe(tool: ToolName, args: dict, fn: Callable[[], ToolResult]) -> ToolResult:
    try:
        return fn()
    except LLMError:
        raise
    except Exception as exc:
        logger.warning("Tool %s failed: %s", tool.value, exc)
        return ToolResult(tool=tool, hits=[], trace=ToolTrace(tool=tool, arguments=args, summary=f"tool error: {exc}"))


def _submit(fn: Callable[[], ToolResult]) -> Future:
    return _POOL.submit(usage.run_in_context(fn))


def _order_hits(results: list[ToolResult], doc_id: str | None) -> list[EvidenceHit]:
    computed, facts, chunks, sections = [], [], [], []
    seen: set[str] = set()
    for r in results:
        for h in r.hits:
            if doc_id and h.doc_id and h.doc_id != doc_id:
                continue
            key = str(h.extra.get("fact_id") or h.chunk_id or "") or f"{h.tool.value}:{h.doc_id}:{h.page_number}:{h.excerpt[:80]}"
            if key in seen:
                continue
            seen.add(key)
            if h.tool is ToolName.STRUCTURED_QUERY and h.extra.get("computed"):
                computed.append(h)
            elif h.tool is ToolName.STRUCTURED_QUERY:
                facts.append(h)
            elif h.tool is ToolName.PAGEINDEX_NAVIGATE:
                sections.append(h)
            else:
                chunks.append(h)
    return computed[:MAX_COMPUTED] + facts[:MAX_FACTS] + chunks + sections[:MAX_SECTIONS]


def _evidence_text(h: EvidenceHit) -> str:
    """What the verifier searches: the excerpt, its section and title context."""
    return " ".join(x for x in (h.excerpt, h.title, str(h.extra.get("context") or "")) if x)


def _evidence_values(h: EvidenceHit) -> list[float]:
    vals = [h.extra.get("value"), h.extra.get("value_abs")]
    return [float(v) for v in vals if isinstance(v, (int, float))]


def _kind(h: EvidenceHit) -> str:
    if h.tool is ToolName.STRUCTURED_QUERY:
        return "computed" if h.extra.get("computed") else "table cell"
    if h.tool is ToolName.PAGEINDEX_NAVIGATE:
        return "section summary"
    return "passage"


def _defang(text: str) -> str:
    return re.sub(r"<\s*/?\s*evidence", "‹evidence", text or "", flags=re.IGNORECASE)


def evidence_blocks(hits: list[EvidenceHit], *, multi_doc: bool = False) -> str:
    blocks = []
    for i, h in enumerate(hits, 1):
        attrs = [f'id="E{i}"', f'page="{h.page_number}"', f'kind="{_kind(h)}"']
        if multi_doc and h.document_name:
            attrs.append(f'document="{_defang(h.document_name)[:80]}"')
        if h.title:
            attrs.append(f'section="{_defang(h.title).replace(chr(34), chr(39))[:160]}"')
        period = h.extra.get("period")
        if period:
            attrs.append(f'period="{_defang(str(period))[:40]}"')
        blocks.append(f"<evidence {' '.join(attrs)}>\n{_defang(h.excerpt)}\n</evidence>")
    return "\n\n".join(blocks) if blocks else "(no evidence was found)"


def answer_user_prompt(question: str, blocks: str, *, history: str = "", notes: list[str] | None = None) -> str:
    parts = [f"question: {question}"]
    if history.strip():
        parts.append("recent conversation:\n" + history)
    if notes:
        parts.append("notes:\n" + "\n".join(f"- {n}" for n in notes))
    parts.append("evidence:\n" + blocks)
    parts.append("Write the answer now.")
    return "\n\n".join(parts)


# --- streaming ------------------------------------------------------------------

_TRAILER = re.compile(r"\n?\s*\**FOLLOW[\s-]?UPS?\**\s*:", re.IGNORECASE)


def _labels(hits: list[EvidenceHit]) -> dict[int, str]:
    return {i: f"[Page {h.page_number}]" for i, h in enumerate(hits, 1)}


def display_text(text: str, labels: dict[int, str]) -> str:
    """``[E2][E5]`` -> ``[Page 12][Page 30]`` (same page once)."""

    def run(m: re.Match) -> str:
        ids = [int(x) for x in CITE.findall(m.group(0))]
        out = list(dict.fromkeys(labels[i] for i in ids if i in labels))
        return (" " if m.group(0).startswith(" ") else "") + "".join(out)

    return re.sub(r" ?(?:\[E\d{1,3}\])+", run, text or "")


class StreamFilter:
    """Shows the answer as it streams: evidence ids become page badges, the FOLLOW-UPS trailer is hidden."""

    def __init__(self, labels: dict[int, str]):
        self.labels = labels
        self.raw = ""
        self.sent = 0  # chars of raw already shown
        self.done = False

    def feed(self, piece: str) -> str:
        self.raw += piece
        return self._release(final=False)

    def finish(self) -> str:
        return self._release(final=True)

    def _release(self, *, final: bool) -> str:
        if self.done:
            return ""
        m = _TRAILER.search(self.raw, self.sent)
        end = m.start() if m else len(self.raw)
        if m:
            self.done = True
        elif not final:
            tail = self.raw[self.sent:end]
            hold = len(tail)
            bracket = tail.rfind("[")
            if bracket != -1 and "]" not in tail[bracket:] and len(tail) - bracket < 8:
                hold = bracket  # wait for "[E12]" to close
            low = tail.lower()
            for k in range(12, 0, -1):  # a trailer may be arriving: "\nFOLLOW-U" (longest match first)
                if low.endswith("\nfollow-ups:"[:k]) or low.endswith("follow-ups:"[:k]) or low.endswith("**follow"[:k]):
                    hold = min(hold, len(tail) - k)
                    break
            end = self.sent + max(0, hold)
        out = self.raw[self.sent:end]
        self.sent = end
        return display_text(out, self.labels)


def split_follow_ups(text: str) -> tuple[str, list[str]]:
    m = _TRAILER.search(text or "")
    if not m:
        return (text or "").strip(), []
    body, tail = text[: m.start()], text[m.end():]
    ups = []
    for line in tail.splitlines():
        line = line.strip().lstrip("-*•").strip()
        if line and line.lower().rstrip(".") != "none":
            ups.append(line)
    return body.strip(), ups[:2]


# --- the agent -------------------------------------------------------------------


@dataclass
class QueryAgent:
    """Compile-once LangGraph runner."""

    deps: QueryAgentDeps
    _graph: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._graph = self._build_graph()

    # The nodes read the per-call run record (timings, streaming sink) from a
    # context variable: callables cannot live in checkpointed state.

    def _build_graph(self):
        deps = self.deps

        def understand_node(state: QueryState) -> QueryState:
            run = _RUN.get() or {}
            question = (state.get("question") or "").strip()
            history = _format_history(list(state.get("messages") or []), max_messages=deps.history_max_messages)
            pinned = deps.doc_id
            catalog = [] if pinned else list(deps.corpus)
            if not pinned and len(catalog) == 1:
                pinned, catalog = catalog[0].document_id, []

            if GREETING.match(question):
                return {"plan": Plan(kind="chitchat", question=question).__dict__, "standalone": question}

            use_llm = deps.planner == "llm" or (deps.planner == "auto" and (bool(history.strip()) or len(catalog) > 1))
            speculative: Future | None = None
            if not history.strip():
                speculative = _submit(lambda: _safe(ToolName.SEMANTIC_SEARCH, {"query": question}, lambda: _search(deps, question, pinned)))

            if use_llm:
                try:
                    with usage.purpose("plan"):
                        plan = llm_plan(deps.llm, question, system=deps.profile.plan_system, history=history, catalog=catalog or None)
                except LLMError as exc:
                    if exc.kind in ("auth", "deadline", "rate_limit"):
                        raise
                    logger.warning("Planner call failed (%s); using the rule-based plan", exc)
                    plan = rules_plan(question)
                    plan.source = "fallback"
                    plan.notes.append(f"planner error: {exc.kind}")
            else:
                plan = rules_plan(question)

            doc = pinned or plan.document_id
            if not doc and catalog and plan.source != "llm":
                doc = _heuristic_route(question, catalog).document_id
            plan.document_id = doc
            run["speculative"] = speculative
            run["speculative_doc"] = pinned
            run["plan_s"] = time.perf_counter() - run.get("t0", time.perf_counter())
            pdf = deps.pdf_path or (_resolve_pdf(deps, doc) if doc else None)
            return {
                "plan": plan.__dict__,
                "standalone": plan.question or question,
                "active_doc_id": doc,
                "doc_id": doc or "",
                "pdf_path": str(pdf) if pdf else None,
            }

        def after_understand(state: QueryState) -> str:
            return "verify" if (state.get("plan") or {}).get("kind") == "chitchat" else "retrieve"

        def retrieve_node(state: QueryState) -> QueryState:
            run = _RUN.get() or {}
            plan = state.get("plan") or {}
            doc = state.get("active_doc_id")
            standalone = state.get("standalone") or state.get("question") or ""
            jobs: list[Future] = []
            speculative: Future | None = run.pop("speculative", None)
            # The search started with the planning call ran on the question as asked (it
            # only starts when there is no conversation to resolve), so it stays valid
            # unless the plan then picked a document the search did not filter on.
            if speculative is not None and run.get("speculative_doc") == doc:
                jobs.append(speculative)
            else:
                if speculative is not None:
                    speculative.cancel()
                jobs.append(_submit(lambda: _safe(ToolName.SEMANTIC_SEARCH, {"query": standalone}, lambda: _search(deps, standalone, doc))))
            if plan.get("facts"):
                spec = plan["facts"]
                jobs.append(_submit(lambda: _safe(ToolName.STRUCTURED_QUERY, spec, lambda: _facts(deps, spec, doc))))
            if plan.get("section") and doc:
                topic = plan["section"]
                jobs.append(_submit(lambda: _safe(ToolName.PAGEINDEX_NAVIGATE, {"topic": topic}, lambda: _sections(deps, topic, doc))))
            results = [j.result() for j in jobs]
            hits = _order_hits(results, doc)
            titles = " ".join({h.document_name for h in hits if h.document_name})
            titles += " " + " ".join(d.document_name for d in deps.corpus if d.document_id == doc)
            missing = missing_scope_terms(standalone, " ".join(_evidence_text(h) for h in hits) + " " + titles)
            run["retrieve_s"] = time.perf_counter() - run.get("t0", time.perf_counter())
            run["hits"], run["traces"], run["missing_terms"] = hits, [r.trace for r in results], missing
            return {}

        def answer_node(state: QueryState) -> QueryState:
            run = _RUN.get() or {}
            hits: list[EvidenceHit] = run.get("hits") or []
            mode = state.get("mode") or deps.mode
            standalone = state.get("standalone") or state.get("question") or ""
            if mode == "audit":
                # a claim is checked as the user wrote it, not as a rewritten question
                standalone = state.get("question") or standalone
            if not hits:
                run["draft"], run["follow_ups"] = f"{NOT_FOUND}: no passage or table in the document matches this question.", []
                return {}
            history = _format_history(list(state.get("messages") or []), max_messages=deps.history_max_messages)
            notes = []
            missing = run.get("missing_terms") or []
            if missing:
                notes.append(
                    "These words from the question appear nowhere in the evidence: "
                    + ", ".join(as_written(standalone, m) for m in missing)
                    + ". If the question depends on them, the answer is not in the evidence."
                )
            multi = len({h.doc_id for h in hits if h.doc_id}) > 1
            prompt = answer_user_prompt(standalone, evidence_blocks(hits, multi_doc=multi), history=history, notes=notes)
            messages = [{"role": "system", "content": deps.profile.answer_prompt(mode)}, {"role": "user", "content": prompt}]
            sink = _TOKEN_SINK.get()
            stream_filter = StreamFilter(_labels(hits))
            with usage.purpose("answer"):
                stream = deps.llm.stream(messages, temperature=0.0, max_tokens=1600 if mode == "detailed" else 900)
                for piece in stream:
                    shown = stream_filter.feed(piece)
                    if shown and sink is not None:
                        if "first_token_s" not in run:
                            run["first_token_s"] = time.perf_counter() - run.get("t0", time.perf_counter())
                        sink(shown)
                rest = stream_filter.finish()
                if rest and sink is not None:
                    run.setdefault("first_token_s", time.perf_counter() - run.get("t0", time.perf_counter()))
                    sink(rest)
            text = stream.result.text if stream.result else stream_filter.raw
            if "first_token_s" not in run:
                run["first_token_s"] = time.perf_counter() - run.get("t0", time.perf_counter())
            body, follow_ups = split_follow_ups(text)
            run["answer_model"] = f"{deps.llm.provider}/{deps.llm.model}"
            run["draft"], run["follow_ups"] = body, follow_ups
            return {}

        def verify_node(state: QueryState) -> QueryState:
            run = _RUN.get() or {}
            plan = state.get("plan") or {}
            mode = state.get("mode") or deps.mode
            question = state.get("question") or ""
            if plan.get("kind") == "chitchat":
                text = _greeting(deps, state.get("active_doc_id") or deps.doc_id)
                sink = _TOKEN_SINK.get()
                if sink is not None:
                    run.setdefault("first_token_s", time.perf_counter() - run.get("t0", time.perf_counter()))
                    sink(text)
                qa = QueryAnswer(
                    question=question, answer=text, provenance=ProvenanceChain(), doc_id=state.get("active_doc_id") or deps.doc_id,
                    status="greeting", mode=mode, prompt_profile=deps.profile.id,
                )
                run["answer"] = qa
                return {"messages": [AIMessage(content=text)]}

            hits: list[EvidenceHit] = run.get("hits") or []
            draft = run.get("draft") or ""
            titles = " ".join({h.document_name for h in hits if h.document_name})
            check = verify_answer(
                draft,
                [_evidence_text(h) for h in hits],
                question=question if mode == "audit" else (state.get("standalone") or question),
                evidence_values=[_evidence_values(h) for h in hits],
                titles=titles + " " + " ".join(d.document_name for d in deps.corpus if d.document_id == state.get("active_doc_id")),
                strict=(mode == "audit"),
            )
            selected = [hits[i - 1] for i in check.cited if 1 <= i <= len(hits)][: deps.max_citations]
            status = "not_found" if check.not_found else "answered"
            if status == "answered" and not selected:
                status = "not_found"
                check.answer = f"{NOT_FOUND}: none of the evidence states this."
            final_text = display_text(check.answer, _labels(hits))
            provenance = ProvenanceChain()
            if status == "answered":
                pdf = state.get("pdf_path") or deps.pdf_path or _resolve_pdf(deps, selected[0].doc_id)
                from src.query.page_map import enrich_hit_printed_page

                selected = [enrich_hit_printed_page(h, pdf_path=pdf) for h in selected]
                provenance = assemble_provenance(selected, pdf_path=pdf, max_citations=deps.max_citations)
                if provenance.is_empty:
                    status = "not_found"
                    final_text = f"{NOT_FOUND}: the cited evidence could not be located in the document."
            traces: list[ToolTrace] = run.get("traces") or []
            qa = QueryAnswer(
                question=question,
                answer=final_text,
                provenance=provenance,
                tool_trace=traces,
                doc_id=state.get("active_doc_id") or deps.doc_id,
                follow_ups=list(run.get("follow_ups") or []) if status == "answered" else [],
                status=status,
                mode=mode,
                prompt_profile=deps.profile.id,
                verification=check.to_dict() | {"plan": {k: plan.get(k) for k in ("source", "facts", "section", "document_id")}},
            )
            run["answer"] = qa
            return {"messages": [AIMessage(content=final_text)]}

        graph = StateGraph(QueryState)
        graph.add_node("understand", understand_node)
        graph.add_node("retrieve", retrieve_node)
        graph.add_node("answer", answer_node)
        graph.add_node("verify", verify_node)
        graph.set_entry_point("understand")
        graph.add_conditional_edges("understand", after_understand, {"retrieve": "retrieve", "verify": "verify"})
        graph.add_edge("retrieve", "answer")
        graph.add_edge("answer", "verify")
        graph.add_edge("verify", END)
        if deps.checkpointer is not None:
            return graph.compile(checkpointer=deps.checkpointer)
        return graph.compile()

    def ask(
        self,
        question: str,
        *,
        thread_id: str | None = None,
        on_token: Callable[[str], None] | None = None,
        mode: str | None = None,
    ) -> QueryAnswer:
        """Answer one question; ``on_token`` receives the answer text as it is written.

        Pass the same ``thread_id`` on later calls to resume conversation memory
        (requires a checkpointer on ``QueryAgentDeps``).

        Raises:
            LLMError: the model provider failed or the answer ran out of time.
        """
        from src.observability.langsmith import tracing_enabled

        question = (question or "").strip()
        mode = normalize_mode(mode or self.deps.mode)
        if not question:
            return QueryAnswer(
                question="", answer=f"{NOT_FOUND}: the question is empty.", provenance=ProvenanceChain(),
                doc_id=self.deps.doc_id, status="not_found", mode=mode, prompt_profile=self.deps.profile.id,
            )

        def _invoke() -> QueryAnswer:
            payload_in: dict[str, Any] = {
                "messages": [HumanMessage(content=question)],
                "question": question,
                "standalone": question,
                "mode": mode,
                "doc_id": self.deps.doc_id or "",
                "active_doc_id": self.deps.doc_id,
                "pdf_path": str(self.deps.pdf_path) if self.deps.pdf_path else None,
                "plan": {},
            }
            run: dict = {"t0": time.perf_counter()}
            run_token, sink_token = _RUN.set(run), _TOKEN_SINK.set(on_token)
            try:
                with usage.deadline(_deadline_seconds()), usage.collect() as events:
                    if self.deps.checkpointer is not None:
                        tid = (thread_id or "default").strip() or "default"
                        self._graph.invoke(payload_in, config=SessionConfig(thread_id=tid).to_runnable_config())
                    else:
                        self._graph.invoke(payload_in)
            finally:
                _RUN.reset(run_token)
                _TOKEN_SINK.reset(sink_token)
            total = time.perf_counter() - run["t0"]
            answer: QueryAnswer | None = run.get("answer")
            if answer is None:  # pragma: no cover - every path ends in verify
                raise RuntimeError("the answer engine finished without an answer")
            data = answer.model_dump(mode="json")
            data["usage"] = usage.summarize(events) | {"answer_model": run.get("answer_model")}
            data["timings"] = {
                "total_s": round(total, 3),
                "first_token_s": round(run.get("first_token_s", total), 3),
                "plan_s": round(run.get("plan_s", 0.0), 3),
                "retrieve_s": round(run.get("retrieve_s", 0.0), 3),
            }
            return QueryAnswer.model_validate(data)

        if not tracing_enabled():
            return _invoke()
        try:
            from langsmith import trace
        except Exception:  # pragma: no cover
            return _invoke()
        with trace(
            name="docmind.query.ask",
            run_type="chain",
            inputs={"question": question, "doc_id": self.deps.doc_id, "thread_id": thread_id, "mode": mode},
            tags=["docmind", "query"],
            metadata={"agent": "QueryAgent", "prompt_profile": self.deps.profile.id},
        ) as tr:
            answer = _invoke()
            try:
                tr.end(outputs={"answer": answer.answer, "status": answer.status, "citations": len(answer.provenance)})
            except Exception:  # pragma: no cover
                pass
            return answer

    def get_messages(self, thread_id: str) -> list[ConversationMessage]:
        """Read persisted turns for a thread (empty if no checkpointer)."""
        if self.deps.checkpointer is None:
            return []
        config = SessionConfig(thread_id=thread_id).to_runnable_config()
        snap = self._graph.get_state(config)
        values = snap.values if snap else {}
        out: list[ConversationMessage] = []
        for msg in list(values.get("messages") or []):
            content = str(getattr(msg, "content", "") or "").strip()
            if not content:
                continue
            mtype = getattr(msg, "type", "")
            role = MessageRole.USER if mtype == "human" else MessageRole.ASSISTANT if mtype == "ai" else MessageRole.SYSTEM
            out.append(ConversationMessage(role=role, content=content))
        return out


def _greeting(deps: QueryAgentDeps, active: str | None) -> str:
    if active:
        name = next((d.document_name for d in deps.corpus if d.document_id == active and d.document_name), None)
        what = f"**{name}**" if name else "this document"
        return f"Hello! I'm ready to help you explore {what}. What would you like to know?"
    return (
        "Hello! Welcome to DocMind \U0001f4c4, your document intelligence assistant. Upload a PDF to get started, "
        "or ask me anything about your documents."
    )


def build_query_agent(
    doc_id: str | None = None,
    *,
    stores: Stores,
    llm: LLMClient | None = None,
    pdf_path: str | Path | None = None,
    pdf_resolver: Callable[[str], Path | None] | None = None,
    embedder: EmbeddingClient | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    corpus: list[CorpusDocument] | None = None,
    max_tool_calls: int = 3,
    mode: str | None = None,
    planner: str | None = None,
    profile: str | None = None,
) -> QueryAgent:
    """Factory: uses ``get_text_client()`` when ``llm`` is omitted.

    Pass ``doc_id`` to pin one document; omit it to let the plan pick from
    ``corpus``. Pass a ``checkpointer`` to keep conversation memory per
    ``thread_id``.
    """
    client = llm if llm is not None else get_text_client()
    if client is None:
        raise RuntimeError(
            "No LLM client available. Set OPENAI_API_KEY (or another provider key) in .env, or pass llm= explicitly."
        )
    from src.config import MAX_CITATIONS, PAGEINDEX_TOP_K, SEMANTIC_TOP_K

    deps = QueryAgentDeps(
        llm=client,
        stores=stores,
        doc_id=doc_id,
        pdf_path=pdf_path,
        pdf_resolver=pdf_resolver,
        embedder=embedder,
        checkpointer=checkpointer,
        corpus=list(corpus or []),
        max_tool_calls=max_tool_calls,
        semantic_top_k=SEMANTIC_TOP_K,
        pageindex_top_k=min(PAGEINDEX_TOP_K, 3),
        max_citations=MAX_CITATIONS,
        profile=get_profile(profile),
        mode=normalize_mode(mode),
    )
    if planner:
        deps.planner = planner
    return QueryAgent(deps)
