"""
Audit Mode: check a claim against a document.

Since M7 this is the answer engine in its ``audit`` mode (see
``src.agents.query_agent``): the same retrieval, an answer that must start
with "Verified:", "Contradicted:" or "Not found in the document:", and the
strict verifier, which removes every sentence that does not cite evidence or
states a number the evidence does not hold. A claim is VERIFIED only when the
checked answer says so and still cites evidence; anything else is
UNVERIFIABLE. It never silently agrees.

V1 had a separate auditor with its own judge prompt, and the API's Audit
Mode switch only wrote a log line (audit P0-9).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.agents.query_agent import QueryAgent, QueryAgentDeps
from src.llm.base import LLMClient
from src.llm.factory import get_text_client
from src.models.provenance import ProvenanceChain
from src.models.query import AuditStatus, AuditVerdict
from src.retrieval.embeddings import EmbeddingClient
from src.stores.base import Stores


@dataclass
class AuditAgentDeps(QueryAgentDeps):
    """Same injectable stores as the answer engine (``use_planner`` is accepted for old callers)."""

    use_planner: bool = False


class AuditAgent:
    def __init__(self, deps: AuditAgentDeps):
        deps.mode = "audit"
        if deps.use_planner:
            deps.planner = "llm"
        self.deps = deps
        self._engine = QueryAgent(deps)

    def audit(self, claim: str) -> AuditVerdict:
        """Check a claim; VERIFIED with citations, or UNVERIFIABLE."""
        claim = (claim or "").strip()
        if not claim:
            return AuditVerdict(claim="", status=AuditStatus.UNVERIFIABLE, rationale="Empty claim cannot be verified.", doc_id=self.deps.doc_id)
        answer = self._engine.ask(claim, mode="audit")
        verified = (
            answer.status == "answered"
            and answer.answer.lstrip("*_ ").lower().startswith("verified")
            and not answer.provenance.is_empty
        )
        return AuditVerdict(
            claim=claim,
            status=AuditStatus.VERIFIED if verified else AuditStatus.UNVERIFIABLE,
            provenance=answer.provenance if verified else ProvenanceChain(),
            rationale=answer.answer,
            doc_id=answer.doc_id or self.deps.doc_id,
            tool_trace=list(answer.tool_trace),
        )


def build_audit_agent(
    doc_id: str,
    *,
    stores: Stores,
    llm: LLMClient | None = None,
    pdf_path: str | Path | None = None,
    embedder: EmbeddingClient | None = None,
    max_tool_calls: int = 3,
    use_planner: bool = False,
) -> AuditAgent:
    """Factory: uses ``get_text_client()`` when ``llm`` is omitted."""
    client = llm if llm is not None else get_text_client()
    if client is None:
        raise RuntimeError(
            "No LLM client available. Set OPENAI_API_KEY (or another provider key) in .env, or pass llm= explicitly."
        )
    return AuditAgent(
        AuditAgentDeps(
            llm=client,
            stores=stores,
            doc_id=doc_id,
            pdf_path=pdf_path,
            embedder=embedder,
            max_tool_calls=max_tool_calls,
            use_planner=use_planner,
        )
    )
