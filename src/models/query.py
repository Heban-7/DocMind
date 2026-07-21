"""
Query / Audit response contracts for Phase 4.

These are the *outputs* of the Query Agent and Audit Mode. Tools return raw
evidence; the agent packages that evidence into a typed answer that always
carries (or explicitly declines) a ProvenanceChain.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.provenance import ProvenanceChain


class ToolName(str, Enum):
    """The three retrieval tools the LangGraph agent is allowed to call."""

    PAGEINDEX_NAVIGATE = "pageindex_navigate"
    SEMANTIC_SEARCH = "semantic_search"
    STRUCTURED_QUERY = "structured_query"


class ToolTrace(BaseModel):
    """One recorded tool call -- useful for demos and debugging the agent."""

    model_config = ConfigDict(frozen=True)

    tool: ToolName
    arguments: dict = Field(default_factory=dict)
    summary: str = Field(
        default="",
        description="human-readable one-liner of what the tool returned",
    )


class QueryAnswer(BaseModel):
    """Natural-language answer plus the provenance that backs it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    answer: str
    provenance: ProvenanceChain
    tool_trace: list[ToolTrace] = Field(default_factory=list)
    doc_id: str | None = Field(
        default=None, description="scoped document id when the query was per-doc"
    )

    @model_validator(mode="after")
    def _require_citations_for_substantive_answers(self) -> QueryAnswer:
        """Refuse silent hallucination: a non-empty answer needs provenance.

        Empty / explicit-refusal answers (e.g. 'I could not find that') may omit
        citations. Everything else must cite at least one source.
        """
        refusal_markers = (
            "could not find",
            "not found",
            "unverifiable",
            "no supporting",
            "i don't know",
            "i do not know",
        )
        lowered = self.answer.strip().lower()
        is_refusal = (not lowered) or any(m in lowered for m in refusal_markers)
        if not is_refusal and self.provenance.is_empty:
            raise ValueError(
                "QueryAnswer with a substantive answer must include at least "
                "one provenance citation."
            )
        return self


class AuditStatus(str, Enum):
    """Closed vocabulary for Audit Mode outcomes."""

    VERIFIED = "verified"
    UNVERIFIABLE = "unverifiable"


class AuditVerdict(BaseModel):
    """Result of checking a claim against the refinery's evidence stores."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim: str
    status: AuditStatus
    provenance: ProvenanceChain = Field(default_factory=ProvenanceChain)
    rationale: str = Field(
        default="",
        description="short explanation of why the claim was verified or not",
    )
    doc_id: str | None = None
    tool_trace: list[ToolTrace] = Field(default_factory=list)

    @model_validator(mode="after")
    def _verified_needs_evidence(self) -> AuditVerdict:
        if self.status is AuditStatus.VERIFIED and self.provenance.is_empty:
            raise ValueError(
                "AuditVerdict status=verified requires a non-empty ProvenanceChain."
            )
        return self
