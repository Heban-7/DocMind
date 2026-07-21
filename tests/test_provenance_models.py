"""Unit tests for Phase 4 provenance / query contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.provenance import BoundingBox, Citation, ProvenanceChain
from src.models.query import (
    AuditStatus,
    AuditVerdict,
    QueryAnswer,
    ToolName,
    ToolTrace,
)


def _citation(**overrides) -> Citation:
    base = dict(
        document_name="sample.pdf",
        page_number=4,
        bbox=BoundingBox.full_page(595.0, 842.0),
        content_hash="abc123",
        chunk_id="chunk-1",
        excerpt="Import tax expenditures were ETB 120.7 billion",
    )
    base.update(overrides)
    return Citation(**base)


def test_bounding_box_full_page():
    box = BoundingBox.full_page(595.0, 842.0)
    assert box.x0 == 0.0 and box.y1 == 842.0
    assert box.page_width == 595.0


def test_provenance_chain_len_and_empty():
    chain = ProvenanceChain(citations=[_citation()])
    assert len(chain) == 1
    assert not chain.is_empty
    assert ProvenanceChain().is_empty


def test_query_answer_requires_citation_for_substantive_text():
    with pytest.raises(ValidationError):
        QueryAnswer(
            question="What was expenditure?",
            answer="Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
            provenance=ProvenanceChain(),
        )


def test_query_answer_allows_refusal_without_citation():
    ans = QueryAnswer(
        question="What was revenue in Mars?",
        answer="I could not find that in the document.",
        provenance=ProvenanceChain(),
    )
    assert ans.provenance.is_empty


def test_query_answer_with_provenance_ok():
    ans = QueryAnswer(
        question="What was expenditure?",
        answer="Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
        provenance=ProvenanceChain(citations=[_citation()]),
        tool_trace=[
            ToolTrace(
                tool=ToolName.SEMANTIC_SEARCH,
                arguments={"query": "import tax expenditures"},
                summary="1 hit on page 4",
            )
        ],
        doc_id="212dc42370e2",
    )
    assert len(ans.provenance) == 1
    assert ans.tool_trace[0].tool is ToolName.SEMANTIC_SEARCH


def test_audit_verified_requires_provenance():
    with pytest.raises(ValidationError):
        AuditVerdict(
            claim="Revenue was $4.2B",
            status=AuditStatus.VERIFIED,
            provenance=ProvenanceChain(),
        )


def test_audit_unverifiable_allows_empty_chain():
    verdict = AuditVerdict(
        claim="Revenue was $4.2B on Mars",
        status=AuditStatus.UNVERIFIABLE,
        rationale="No matching evidence in FactTable or LDUs.",
    )
    assert verdict.status is AuditStatus.UNVERIFIABLE
    assert verdict.provenance.is_empty


def test_audit_verified_with_citation():
    verdict = AuditVerdict(
        claim="Import tax expenditures were ETB 120.7 billion",
        status=AuditStatus.VERIFIED,
        provenance=ProvenanceChain(citations=[_citation()]),
        rationale="Exact figure found in Executive summary LDU.",
    )
    assert verdict.status is AuditStatus.VERIFIED
    assert len(verdict.provenance) == 1
