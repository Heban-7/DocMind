"""Tests for dual page numbering (physical vs printed PageLabels)."""

from __future__ import annotations

import pytest

from src.config import DATA_DIR, DEFAULT_SAMPLE_PDF
from src.models.provenance import BoundingBox, Citation
from src.models.query import ToolName
from src.query.evidence import EvidenceHit
from src.query.page_map import (
    clear_page_map_cache,
    format_page_reference,
    load_page_map,
    resolve_printed_page,
)
from src.query.provenance import citation_from_hit

ANNUAL_2017 = DATA_DIR / "Annual_Report_JUNE-2017.pdf"
ANNUAL_2019 = DATA_DIR / "Annual_Report_JUNE-2019.pdf"


def test_format_page_reference_collapse_and_dual():
    assert format_page_reference(8) == "p.8"
    assert format_page_reference(8, None) == "p.8"
    assert format_page_reference(8, "8") == "p.8"
    assert format_page_reference(33, "1") == "PDF p.33 (document p.1)"
    assert format_page_reference(5, "III") == "PDF p.5 (document p.III)"


def test_citation_page_ref_backward_compatible():
    """Existing citations without printed_page still validate and display."""
    c = Citation(
        document_name="sample.pdf",
        page_number=4,
        bbox=BoundingBox.full_page(595.0, 842.0),
        content_hash="abc",
        excerpt="hello",
    )
    assert c.printed_page is None
    assert c.page_ref == "p.4"
    assert c.page_number == 4


def test_citation_from_hit_without_pdf_keeps_physical_only():
    hit = EvidenceHit(
        tool=ToolName.SEMANTIC_SEARCH,
        document_name="sample.pdf",
        page_number=4,
        content_hash="h",
        excerpt="x",
    )
    citation = citation_from_hit(hit, pdf_path=None)
    assert citation.page_number == 4
    assert citation.printed_page is None
    assert citation.page_ref == "p.4"


@pytest.mark.skipif(not DEFAULT_SAMPLE_PDF.exists(), reason="sample.pdf missing")
def test_sample_pdf_without_labels_is_identity():
    clear_page_map_cache()
    page_map = load_page_map(DEFAULT_SAMPLE_PDF)
    assert page_map is not None
    # sample.pdf has empty PageLabels -> no printed override
    assert page_map.printed_label(1) is None
    assert resolve_printed_page(DEFAULT_SAMPLE_PDF, 1) is None
    citation = citation_from_hit(
        EvidenceHit(
            tool=ToolName.SEMANTIC_SEARCH,
            document_name="sample.pdf",
            page_number=1,
            content_hash="h",
            excerpt="cover",
        ),
        pdf_path=DEFAULT_SAMPLE_PDF,
    )
    assert citation.page_number == 1
    assert citation.printed_page is None


@pytest.mark.skipif(not ANNUAL_2017.exists(), reason="Annual_Report_JUNE-2017.pdf missing")
def test_annual_2017_body_page_labels():
    clear_page_map_cache()
    # Front matter uses letters/romans; body arabic starts at physical 33.
    assert resolve_printed_page(ANNUAL_2017, 1) == "A"
    assert resolve_printed_page(ANNUAL_2017, 3) == "I"
    assert resolve_printed_page(ANNUAL_2017, 33) == "1"
    assert resolve_printed_page(ANNUAL_2017, 34) == "2"

    citation = citation_from_hit(
        EvidenceHit(
            tool=ToolName.SEMANTIC_SEARCH,
            document_name=ANNUAL_2017.name,
            page_number=33,
            content_hash="h",
            excerpt="body start",
        ),
        pdf_path=ANNUAL_2017,
    )
    assert citation.page_number == 33
    assert citation.printed_page == "1"
    assert citation.page_ref == "PDF p.33 (document p.1)"


@pytest.mark.skipif(not ANNUAL_2019.exists(), reason="Annual_Report_JUNE-2019.pdf missing")
def test_annual_2019_restart_labels():
    clear_page_map_cache()
    # Cover sheets labeled 1..3 then body restarts at 1 on physical page 4.
    assert resolve_printed_page(ANNUAL_2019, 1) == "1"
    assert resolve_printed_page(ANNUAL_2019, 4) == "1"
    assert format_page_reference(4, "1") == "PDF p.4 (document p.1)"
