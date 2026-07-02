"""
The Triage Agent.

Pipeline for one PDF:

    open -> sample pages -> measure signals (signals.py)
         -> aggregate -> decide (origin / layout / language / domain / cost)
         -> emit a strictly-typed DocumentProfile -> persist as JSON.

The decision functions below are deliberately PURE (numbers in, label out) so
they can be unit-tested without any PDF. The TriageAgent only wires them to
real pdfplumber evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pdfplumber

from src.agents.domain import DomainClassifier, build_default_domain_classifier
from src.agents.signals import detect_language, extract_page_signals
from src.config import DEFAULT_SAMPLE_PDF, PROFILES_DIR, TRIAGE_VERSION, Thresholds
from src.models.document_profile import (
    DocumentProfile,
    DocumentSignals,
    DomainHint,
    ExtractionCost,
    LanguageGuess,
    LayoutComplexity,
    OriginType,
    PageSignals,
)

# Cap how much text we feed to the language/domain heuristics (speed guard).
_MAX_TEXT_CHARS = 40_000


# --- Pure decision functions (numbers in -> label out) ----------------------
def classify_origin(
    text_page_ratio: float,
    scanned_page_ratio: float,
    form_field_page_ratio: float,
) -> OriginType:
    """Decide how the document physically stores its content."""
    if form_field_page_ratio >= Thresholds.FORM_DOC_PAGE_RATIO:
        return OriginType.FORM_FILLABLE
    if text_page_ratio >= Thresholds.DIGITAL_DOC_PAGE_RATIO:
        return OriginType.NATIVE_DIGITAL
    if scanned_page_ratio >= Thresholds.SCANNED_DOC_PAGE_RATIO:
        return OriginType.SCANNED_IMAGE
    return OriginType.MIXED


def classify_layout(
    table_page_ratio: float,
    avg_image_area_ratio: float,
    multi_column_page_ratio: float,
) -> LayoutComplexity:
    """Decide the dominant layout. One strong signal wins; several -> mixed."""
    strong: list[LayoutComplexity] = []
    if table_page_ratio >= Thresholds.TABLE_HEAVY_PAGE_RATIO:
        strong.append(LayoutComplexity.TABLE_HEAVY)
    if avg_image_area_ratio >= Thresholds.FIGURE_HEAVY_IMAGE_RATIO:
        strong.append(LayoutComplexity.FIGURE_HEAVY)
    if multi_column_page_ratio >= Thresholds.MULTI_COLUMN_PAGE_RATIO:
        strong.append(LayoutComplexity.MULTI_COLUMN)

    if not strong:
        return LayoutComplexity.SINGLE_COLUMN
    if len(strong) == 1:
        return strong[0]
    return LayoutComplexity.MIXED


def estimate_cost(origin: OriginType, layout: LayoutComplexity) -> ExtractionCost:
    """Map (origin, layout) to the cheapest sufficient extraction tier."""
    if origin == OriginType.SCANNED_IMAGE:
        return ExtractionCost.NEEDS_VISION_MODEL
    if layout != LayoutComplexity.SINGLE_COLUMN:
        return ExtractionCost.NEEDS_LAYOUT_MODEL
    if origin == OriginType.NATIVE_DIGITAL:
        return ExtractionCost.FAST_TEXT_SUFFICIENT
    # mixed origin or form, simple layout: layout model is the safe default.
    return ExtractionCost.NEEDS_LAYOUT_MODEL


def aggregate_signals(
    page_signals: list[PageSignals], page_count: int
) -> DocumentSignals:
    """Roll per-page evidence up into document-level statistics."""
    analyzed = len(page_signals)
    if analyzed == 0:
        return DocumentSignals(
            page_count=page_count,
            pages_analyzed=0,
            text_page_ratio=0.0,
            scanned_page_ratio=0.0,
            sparse_page_ratio=0.0,
            avg_char_density=0.0,
            avg_image_area_ratio=0.0,
            max_image_area_ratio=0.0,
            table_page_ratio=0.0,
            avg_table_area_ratio=0.0,
            multi_column_page_ratio=0.0,
            form_field_page_ratio=0.0,
            avg_math_symbol_ratio=0.0,
            page_signals=[],
        )

    def ratio(predicate) -> float:
        return sum(1 for p in page_signals if predicate(p)) / analyzed

    return DocumentSignals(
        page_count=page_count,
        pages_analyzed=analyzed,
        text_page_ratio=ratio(lambda p: p.page_class == "text"),
        scanned_page_ratio=ratio(lambda p: p.page_class == "scanned"),
        sparse_page_ratio=ratio(lambda p: p.page_class == "sparse"),
        avg_char_density=sum(p.char_density for p in page_signals) / analyzed,
        avg_image_area_ratio=sum(p.image_area_ratio for p in page_signals) / analyzed,
        max_image_area_ratio=max(p.image_area_ratio for p in page_signals),
        table_page_ratio=ratio(lambda p: p.table_count > 0),
        avg_table_area_ratio=sum(p.table_area_ratio for p in page_signals) / analyzed,
        multi_column_page_ratio=ratio(lambda p: p.column_estimate >= 2),
        form_field_page_ratio=ratio(lambda p: p.has_form_fields),
        avg_math_symbol_ratio=sum(p.math_symbol_ratio for p in page_signals)
        / analyzed,
        page_signals=page_signals,
    )


# --- Helpers ----------------------------------------------------------------
def compute_doc_id(pdf_path: Path) -> str:
    """Stable content hash (first 12 hex of SHA-256) -- same file, same id."""
    digest = hashlib.sha256()
    with open(pdf_path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:12]


def sample_page_indices(page_count: int, max_pages: int) -> list[int]:
    """Pick up to `max_pages` page indices spread evenly across the document."""
    if page_count <= max_pages:
        return list(range(page_count))
    step = page_count / max_pages
    return sorted({int(i * step) for i in range(max_pages)})


def resolve_sample_size(page_count: int) -> int:
    """Adaptive sample size: ~5% of pages, clamped to [SAMPLE_MIN, SAMPLE_MAX].

    A 20-page doc samples the floor (12); a 600-page doc samples the ceiling
    (24). Cheap to raise because triage only reads text, it never renders.
    """
    proportional = math.ceil(page_count * Thresholds.SAMPLE_FRACTION)
    bounded = max(Thresholds.SAMPLE_MIN_PAGES, proportional)
    return min(Thresholds.SAMPLE_MAX_PAGES, bounded)


# --- The agent --------------------------------------------------------------
class TriageAgent:
    """Inspects a PDF and produces a strictly-typed DocumentProfile."""

    def __init__(
        self,
        domain_classifier: DomainClassifier | None = None,
        max_pages: int | None = None,
        profiles_dir: Path = PROFILES_DIR,
    ):
        # max_pages=None means "decide adaptively from the page count".
        # Default classifier is LLM-with-keyword-fallback when a key is present,
        # else keyword-only (fully offline).
        self.domain_classifier = (
            domain_classifier or build_default_domain_classifier()
        )
        self.max_pages = max_pages
        self.profiles_dir = profiles_dir

    def profile(self, pdf_path: Path | str) -> DocumentProfile:
        """Run the full triage and return the profile (without saving)."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"No PDF found at '{pdf_path}'.")

        page_signals: list[PageSignals] = []
        text_parts: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            sample_size = self.max_pages or resolve_sample_size(page_count)
            for idx in sample_page_indices(page_count, sample_size):
                page = pdf.pages[idx]
                page_signals.append(extract_page_signals(page, idx + 1))
                if sum(len(t) for t in text_parts) < _MAX_TEXT_CHARS:
                    text_parts.append(page.extract_text() or "")

        signals = aggregate_signals(page_signals, page_count)
        sampled_text = "\n".join(text_parts)[:_MAX_TEXT_CHARS]

        # --- Decisions + a human-readable reasoning trace. ----------------
        reasoning: list[str] = []

        origin = classify_origin(
            signals.text_page_ratio,
            signals.scanned_page_ratio,
            signals.form_field_page_ratio,
        )
        reasoning.append(
            f"origin={origin.value}: text_pages={signals.text_page_ratio:.0%}, "
            f"scanned_pages={signals.scanned_page_ratio:.0%}, "
            f"avg_char_density={signals.avg_char_density:.1f}/in^2"
        )

        layout = classify_layout(
            signals.table_page_ratio,
            signals.avg_image_area_ratio,
            signals.multi_column_page_ratio,
        )
        reasoning.append(
            f"layout={layout.value}: table_pages={signals.table_page_ratio:.0%}, "
            f"avg_image_area={signals.avg_image_area_ratio:.0%}, "
            f"multi_col_pages={signals.multi_column_page_ratio:.0%}"
        )

        lang_code, lang_conf = detect_language(sampled_text)
        language = LanguageGuess(code=lang_code, confidence=lang_conf)
        reasoning.append(f"language={lang_code} (confidence={lang_conf:.0%})")

        domain, domain_conf = self.domain_classifier.classify(sampled_text)
        reasoning.append(f"domain={domain.value} (confidence={domain_conf:.0%})")

        cost = estimate_cost(origin, layout)
        reasoning.append(
            f"cost={cost.value}: derived from origin '{origin.value}' "
            f"and layout '{layout.value}'"
        )

        return DocumentProfile(
            doc_id=compute_doc_id(pdf_path),
            source_filename=pdf_path.name,
            source_path=str(pdf_path),
            page_count=page_count,
            origin_type=origin,
            layout_complexity=layout,
            language=language,
            domain_hint=domain,
            domain_confidence=domain_conf,
            estimated_cost=cost,
            signals=signals,
            reasoning=reasoning,
            triage_version=TRIAGE_VERSION,
        )

    def save_profile(self, profile: DocumentProfile) -> Path:
        """Persist a profile to .refinery/profiles/{doc_id}.json."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.profiles_dir / f"{profile.doc_id}.json"
        out_path.write_text(
            profile.model_dump_json(indent=2), encoding="utf-8"
        )
        return out_path

    def profile_and_save(self, pdf_path: Path | str) -> tuple[DocumentProfile, Path]:
        profile = self.profile(pdf_path)
        return profile, self.save_profile(profile)


# --- CLI demo ---------------------------------------------------------------
def _print_summary(profile: DocumentProfile, saved_to: Path) -> None:
    print("=" * 70)
    print("DocMind | Phase 1 | Triage Profile")
    print("=" * 70)
    print(f"File           : {profile.source_filename}")
    print(f"Doc ID         : {profile.doc_id}")
    print(f"Pages          : {profile.page_count} "
          f"(analyzed {profile.signals.pages_analyzed})")
    print("-" * 70)
    print(f"Origin type    : {profile.origin_type.value}")
    print(f"Layout         : {profile.layout_complexity.value}")
    print(f"Language       : {profile.language.code} "
          f"({profile.language.confidence:.0%})")
    print(f"Domain hint    : {profile.domain_hint.value} "
          f"({profile.domain_confidence:.0%})")
    print(f"Est. cost tier : {profile.estimated_cost.value}")
    print("-" * 70)
    print("Reasoning:")
    for line in profile.reasoning:
        print(f"  - {line}")
    print("-" * 70)
    print(f"Profile saved  : {saved_to}")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DocMind Triage Agent.")
    parser.add_argument(
        "pdf",
        nargs="?",
        default=str(DEFAULT_SAMPLE_PDF),
        help="Path to a PDF (defaults to data/data/sample.pdf).",
    )
    args = parser.parse_args()

    agent = TriageAgent()
    profile, saved_to = agent.profile_and_save(args.pdf)
    _print_summary(profile, saved_to)


if __name__ == "__main__":
    main()
