"""
Central configuration for the DocMind Refinery.

Everything that is "tunable" or "environment-specific" lives here so that no
other module hardcodes a path or a magic number. In Phase 2 the THRESHOLDS
below will be externalized to `rubric/extraction_rules.yaml`; for Phase 1 we
keep them as named, justified constants in one obvious place.
"""

from __future__ import annotations

from pathlib import Path

# --- Paths (resolved from this file, so they work from any working dir) -----
# src/config.py -> parents[1] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "data"
DEFAULT_SAMPLE_PDF = DATA_DIR / "sample.pdf"

REFINERY_DIR = PROJECT_ROOT / ".refinery"
PROFILES_DIR = REFINERY_DIR / "profiles"
EXTRACTIONS_DIR = REFINERY_DIR / "extractions"

# Memory guard for the heavy Docling-based engines (layout/vision): the most
# pages to process in a single run. Docling rasterizes pages for its layout
# models, so unbounded multi-hundred-page PDFs can exhaust RAM. Raise this on
# a larger machine; set to None to process the entire document.
EXTRACTION_MAX_PAGES: int | None = 10

# Bumped whenever the triage heuristics change, so stored profiles are traceable
# back to the logic that produced them.
TRIAGE_VERSION = "1.0.0"


# --- Triage heuristic thresholds --------------------------------------------
# These are the empirically-grounded "dials" of the Triage Agent. Each is a
# plain number with a justification, ready to be moved into a YAML file later.
class Thresholds:
    """Tunable decision boundaries for the heuristic Triage Agent."""

    # How many pages to actually parse on large documents. Triage only needs a
    # representative sample, not every page, to characterize a document.
    MAX_PAGES_TO_ANALYZE: int = 12

    # ORIGIN: a page needs at least this many embedded characters to count as a
    # real "text layer" (digital) page. Below this it is text-empty.
    MIN_CHARS_PER_TEXT_PAGE: int = 100

    # ORIGIN: a page whose images cover at least this fraction of its area is
    # "image dominated" (the hallmark of a scanned page).
    IMAGE_DOMINANCE_RATIO: float = 0.50

    # ORIGIN (document level): fraction of analyzed pages that must be text-like
    # to call the whole document natively digital...
    DIGITAL_DOC_PAGE_RATIO: float = 0.80
    # ...or scanned to call the whole document a scanned image.
    SCANNED_DOC_PAGE_RATIO: float = 0.80
    # Fraction of pages that must carry interactive form widgets to be a form.
    FORM_DOC_PAGE_RATIO: float = 0.50

    # LAYOUT: fraction of analyzed pages that contain a detected table for the
    # document to be considered table-heavy.
    TABLE_HEAVY_PAGE_RATIO: float = 0.40
    # LAYOUT: average image-area coverage across pages to be figure-heavy.
    FIGURE_HEAVY_IMAGE_RATIO: float = 0.40
    # LAYOUT: fraction of analyzed pages detected as multi-column.
    MULTI_COLUMN_PAGE_RATIO: float = 0.40

    # DOMAIN: minimum confidence (share of keyword hits) for a specific domain;
    # below this we fall back to "general".
    DOMAIN_MIN_CONFIDENCE: float = 0.34
