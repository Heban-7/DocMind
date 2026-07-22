"""Unit tests for provenance assembly + page bbox resolution (Step 6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import DEFAULT_SAMPLE_PDF
from src.models.provenance import BoundingBox
from src.models.query import ToolName, ToolTrace
from src.query.bbox import clear_page_size_cache, resolve_page_bbox
from src.query.evidence import EvidenceHit, ToolResult
from src.query.provenance import assemble_provenance, citation_from_hit


def _hit(**overrides) -> EvidenceHit:
    base = dict(
        tool=ToolName.SEMANTIC_SEARCH,
        document_name="sample.pdf",
        doc_id="abc",
        page_number=4,
        content_hash="hash-aaa",
        chunk_id="chunk-1",
        excerpt="Import tax expenditures were ETB 120.7 billion",
        title="Executive summary",
        score=0.9,
    )
    base.update(overrides)
    return EvidenceHit(**base)


def test_unresolved_bbox_when_pdf_missing():
    clear_page_size_cache()
    box = resolve_page_bbox(None, 1)
    assert not box.is_resolved
    assert box.x1 == 0.0


def test_unresolved_bbox_when_path_missing(tmp_path: Path):
    clear_page_size_cache()
    box = resolve_page_bbox(tmp_path / "nope.pdf", 1)
    assert not box.is_resolved


@pytest.mark.skipif(not DEFAULT_SAMPLE_PDF.exists(), reason="sample.pdf missing")
def test_resolve_page_bbox_from_real_pdf():
    clear_page_size_cache()
    box = resolve_page_bbox(DEFAULT_SAMPLE_PDF, 1)
    assert box.is_resolved
    assert box.x1 > 100
    assert box.y1 > 100
    assert box.page_width == box.x1
    assert box.page_height == box.y1


def test_citation_from_hit_without_pdf():
    citation = citation_from_hit(_hit(), pdf_path=None)
    assert citation.document_name == "sample.pdf"
    assert citation.page_number == 4
    assert citation.content_hash == "hash-aaa"
    assert not citation.bbox.is_resolved


@pytest.mark.skipif(not DEFAULT_SAMPLE_PDF.exists(), reason="sample.pdf missing")
def test_assemble_provenance_with_pdf_bbox():
    clear_page_size_cache()
    same = "Import tax expenditures were ETB 120.7 billion"
    chain = assemble_provenance(
        [_hit(excerpt=same), _hit(excerpt=same, content_hash="hash-aaa")],
        pdf_path=DEFAULT_SAMPLE_PDF,
    )
    # Second hit deduped (same doc/page/hash/excerpt prefix)
    assert len(chain) == 1
    assert chain.citations[0].bbox.is_resolved


def test_assemble_from_tool_results_and_skip_empty():
    tools = [
        ToolResult(
            tool=ToolName.STRUCTURED_QUERY,
            hits=[
                _hit(tool=ToolName.STRUCTURED_QUERY, content_hash="h2", excerpt="VAT 44.6"),
            ],
            trace=ToolTrace(tool=ToolName.STRUCTURED_QUERY, summary="1"),
        ),
        ToolResult(
            tool=ToolName.PAGEINDEX_NAVIGATE,
            hits=[
                EvidenceHit(
                    tool=ToolName.PAGEINDEX_NAVIGATE,
                    page_number=1,
                    excerpt="",
                    content_hash="",
                )
            ],
            trace=ToolTrace(tool=ToolName.PAGEINDEX_NAVIGATE, summary="empty"),
        ),
    ]
    chain = assemble_provenance(tools, pdf_path=None)
    assert len(chain) == 1
    assert "VAT" in chain.citations[0].excerpt


def test_bounding_box_helpers():
    full = BoundingBox.full_page(595.0, 842.0)
    assert full.is_resolved
    assert not BoundingBox.unresolved().is_resolved
