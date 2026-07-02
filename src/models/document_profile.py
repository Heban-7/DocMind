"""
Typed schemas for the Triage stage.

These Pydantic models are the *contract* every downstream stage relies on. If a
value is the wrong type or an impossible category, Pydantic rejects it at the
boundary -- so a bad profile can never silently flow into extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# --- Classification vocabularies (closed sets of allowed values) ------------
class OriginType(str, Enum):
    """How the document's content physically exists on the page."""

    NATIVE_DIGITAL = "native_digital"  # real, selectable text layer
    SCANNED_IMAGE = "scanned_image"  # pixels only, needs OCR/vision
    MIXED = "mixed"  # some digital pages, some scanned
    FORM_FILLABLE = "form_fillable"  # interactive AcroForm widgets


class LayoutComplexity(str, Enum):
    """The geometric arrangement of content on the page."""

    SINGLE_COLUMN = "single_column"
    MULTI_COLUMN = "multi_column"
    TABLE_HEAVY = "table_heavy"
    FIGURE_HEAVY = "figure_heavy"
    MIXED = "mixed"


class DomainHint(str, Enum):
    """Subject-matter hint used later to pick a prompt/extraction strategy."""

    FINANCIAL = "financial"
    LEGAL = "legal"
    TECHNICAL = "technical"
    MEDICAL = "medical"
    GENERAL = "general"


class ExtractionCost(str, Enum):
    """Which extraction tier the downstream router should budget for."""

    FAST_TEXT_SUFFICIENT = "fast_text_sufficient"  # Strategy A (cheap)
    NEEDS_LAYOUT_MODEL = "needs_layout_model"  # Strategy B (medium)
    NEEDS_VISION_MODEL = "needs_vision_model"  # Strategy C (expensive)


# --- Sub-models -------------------------------------------------------------
class LanguageGuess(BaseModel):
    """A detected language with how confident we are in it."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(description="ISO-639-1-ish code, or 'und' if undetermined")
    confidence: float = Field(ge=0.0, le=1.0)


class PageSignals(BaseModel):
    """The raw, measured evidence gathered from a single page."""

    page_number: int = Field(ge=1)
    width: float
    height: float
    char_count: int = Field(ge=0)
    char_density: float = Field(ge=0.0, description="characters per square inch")
    word_count: int = Field(ge=0)
    image_area_ratio: float = Field(ge=0.0, le=1.0)
    table_count: int = Field(ge=0)
    table_area_ratio: float = Field(ge=0.0, le=1.0)
    column_estimate: int = Field(ge=1)
    math_symbol_ratio: float = Field(
        ge=0.0, le=1.0, description="share of math/scientific symbols among chars"
    )
    has_fonts: bool
    has_form_fields: bool
    page_class: str = Field(description="text | scanned | sparse")


class DocumentSignals(BaseModel):
    """Per-page evidence rolled up into document-level statistics."""

    page_count: int = Field(ge=0)
    pages_analyzed: int = Field(ge=0)
    text_page_ratio: float = Field(ge=0.0, le=1.0)
    scanned_page_ratio: float = Field(ge=0.0, le=1.0)
    sparse_page_ratio: float = Field(ge=0.0, le=1.0)
    avg_char_density: float = Field(ge=0.0)
    avg_image_area_ratio: float = Field(ge=0.0, le=1.0)
    max_image_area_ratio: float = Field(ge=0.0, le=1.0)
    table_page_ratio: float = Field(ge=0.0, le=1.0)
    avg_table_area_ratio: float = Field(ge=0.0, le=1.0)
    multi_column_page_ratio: float = Field(ge=0.0, le=1.0)
    form_field_page_ratio: float = Field(ge=0.0, le=1.0)
    avg_math_symbol_ratio: float = Field(ge=0.0, le=1.0)
    page_signals: list[PageSignals] = Field(default_factory=list)


# --- The top-level deliverable ----------------------------------------------
class DocumentProfile(BaseModel):
    """The Triage Agent's verdict: a strictly-typed characterization of a PDF."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(description="stable content hash (first 12 hex chars)")
    source_filename: str
    source_path: str
    page_count: int = Field(ge=0)

    origin_type: OriginType
    layout_complexity: LayoutComplexity
    language: LanguageGuess
    domain_hint: DomainHint
    domain_confidence: float = Field(ge=0.0, le=1.0)
    estimated_cost: ExtractionCost

    signals: DocumentSignals
    reasoning: list[str] = Field(
        default_factory=list,
        description="human-readable trace of why each label was chosen",
    )

    triage_version: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def strategy_tier(self) -> ExtractionCost:
        """The extraction tier the downstream router should select.

        A read-only alias of `estimated_cost`, exposed under the name the
        Extraction Router speaks in. Keeps Phase 1's schema unchanged while
        giving Phase 2 a clearly-named hook to switch on.
        """
        return self.estimated_cost
