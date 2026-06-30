"""
Integration tests: run the real TriageAgent against known corpus documents.

Requirement #5: "given a known document type, the profile must classify
correctly." These assert the headline verdict (origin + cost tier) for a
known digital and a known scanned document, and prove the saved JSON profile
round-trips back into a validated DocumentProfile.

Tests skip gracefully if the corpus PDFs are not present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.triage import TriageAgent
from src.config import DATA_DIR
from src.models.document_profile import (
    DocumentProfile,
    ExtractionCost,
    OriginType,
)

# A small page sample keeps these tests quick while staying representative.
SAMPLE_PAGES = 6

DIGITAL_PDF = DATA_DIR / "sample.pdf"
SCANNED_PDF = DATA_DIR / "Audit Report - 2023.pdf"


def _require(path: Path):
    if not path.exists():
        pytest.skip(f"corpus file not available: {path.name}")


def test_native_digital_document_is_classified_as_digital():
    _require(DIGITAL_PDF)
    profile = TriageAgent(max_pages=SAMPLE_PAGES).profile(DIGITAL_PDF)

    assert profile.origin_type == OriginType.NATIVE_DIGITAL
    # A digital doc must never be routed to the expensive vision tier.
    assert profile.estimated_cost != ExtractionCost.NEEDS_VISION_MODEL
    assert profile.language.code == "en"


def test_scanned_document_is_classified_as_scanned_and_needs_vision():
    _require(SCANNED_PDF)
    profile = TriageAgent(max_pages=SAMPLE_PAGES).profile(SCANNED_PDF)

    assert profile.origin_type == OriginType.SCANNED_IMAGE
    assert profile.estimated_cost == ExtractionCost.NEEDS_VISION_MODEL


def test_profile_saves_and_round_trips(tmp_path):
    _require(DIGITAL_PDF)
    agent = TriageAgent(max_pages=SAMPLE_PAGES, profiles_dir=tmp_path)

    profile, saved_to = agent.profile_and_save(DIGITAL_PDF)

    assert saved_to.exists()
    assert saved_to.name == f"{profile.doc_id}.json"

    # The persisted JSON must validate back into the same typed model.
    reloaded = DocumentProfile.model_validate_json(
        saved_to.read_text(encoding="utf-8")
    )
    assert reloaded.doc_id == profile.doc_id
    assert reloaded.origin_type == profile.origin_type


def test_doc_id_is_stable_for_same_file():
    _require(DIGITAL_PDF)
    agent = TriageAgent(max_pages=SAMPLE_PAGES)
    first = agent.profile(DIGITAL_PDF)
    second = agent.profile(DIGITAL_PDF)
    assert first.doc_id == second.doc_id
