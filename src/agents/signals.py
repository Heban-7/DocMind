"""
Evidence gathering: turn raw pdfplumber page data into measured `PageSignals`.

This module does NO decision-making. It only *measures* (chars, images,
tables, columns, fonts, scripts). Keeping measurement separate from judgement
makes both halves independently testable and easy to reason about.
"""

from __future__ import annotations

from src.config import Thresholds
from src.models.document_profile import PageSignals

# Unicode block for Ethiopic script (Amharic/Ge'ez) -- relevant to this corpus.
_ETHIOPIC_START = 0x1200
_ETHIOPIC_END = 0x137F


def _rect_area(x0: float, top: float, x1: float, bottom: float) -> float:
    """Area of a bounding box, clamped so negative/garbage boxes count as 0."""
    return max(0.0, x1 - x0) * max(0.0, bottom - top)


def estimate_column_count(words: list[dict], page_width: float) -> int:
    """Estimate text columns by looking for an empty vertical 'gutter'.

    Heuristic: project each word onto the horizontal axis (its center as a
    fraction of page width). A two-column page has lots of words on the left
    and right but a near-empty band down the middle.
    """
    if not words or page_width <= 0:
        return 1

    centers = [((w["x0"] + w["x1"]) / 2.0) / page_width for w in words]
    n = len(centers)
    if n < 30:  # too little text to judge columns reliably
        return 1

    left = sum(1 for c in centers if c < 0.42)
    middle = sum(1 for c in centers if 0.42 <= c <= 0.58)
    right = sum(1 for c in centers if c > 0.58)

    both_sides_busy = (left / n) > 0.25 and (right / n) > 0.25
    middle_is_gutter = (middle / n) < 0.10
    return 2 if both_sides_busy and middle_is_gutter else 1


def page_has_form_widgets(page) -> bool:
    """Best-effort detection of interactive form fields (AcroForm widgets)."""
    try:
        for annot in page.annots or []:
            subtype = annot.get("subtype") or annot.get("Subtype")
            data = annot.get("data") or {}
            subtype = subtype or data.get("Subtype")
            if subtype and "Widget" in str(subtype):
                return True
    except Exception:
        pass
    return False


def classify_page(char_count: int, image_area_ratio: float) -> str:
    """Label a single page as text / scanned / sparse from its raw signals."""
    if char_count >= Thresholds.MIN_CHARS_PER_TEXT_PAGE:
        return "text"
    if image_area_ratio >= Thresholds.IMAGE_DOMINANCE_RATIO:
        return "scanned"
    return "sparse"  # near-empty: not enough text, not clearly an image


def detect_language(text: str) -> tuple[str, float]:
    """Detect language by Unicode script ratio (Latin vs Ethiopic).

    Returns (code, confidence). 'und' (undetermined) when there is no text --
    which is itself a useful signal that a page is likely scanned.
    """
    latin = 0
    ethiopic = 0
    for ch in text:
        codepoint = ord(ch)
        if _ETHIOPIC_START <= codepoint <= _ETHIOPIC_END:
            ethiopic += 1
        elif ch.isascii() and ch.isalpha():
            latin += 1

    total = latin + ethiopic
    if total == 0:
        return ("und", 0.0)
    if ethiopic >= latin:
        return ("am", ethiopic / total)
    return ("en", latin / total)


def extract_page_signals(page, page_number: int) -> PageSignals:
    """Measure every signal we care about for a single pdfplumber page."""
    width = float(page.width)
    height = float(page.height)
    area_points = width * height
    area_sq_inches = (width / 72.0) * (height / 72.0)

    chars = page.chars or []
    char_count = len(chars)
    char_density = char_count / area_sq_inches if area_sq_inches > 0 else 0.0

    words = page.extract_words() or []
    word_count = len(words)

    image_area = sum(
        _rect_area(
            float(img["x0"]), float(img["top"]), float(img["x1"]), float(img["bottom"])
        )
        for img in (page.images or [])
    )
    image_area_ratio = min(1.0, image_area / area_points) if area_points else 0.0

    try:
        tables = page.find_tables()
    except Exception:
        tables = []
    table_area = sum(
        _rect_area(t.bbox[0], t.bbox[1], t.bbox[2], t.bbox[3]) for t in tables
    )
    table_area_ratio = min(1.0, table_area / area_points) if area_points else 0.0

    has_fonts = any(c.get("fontname") for c in chars)

    return PageSignals(
        page_number=page_number,
        width=width,
        height=height,
        char_count=char_count,
        char_density=char_density,
        word_count=word_count,
        image_area_ratio=image_area_ratio,
        table_count=len(tables),
        table_area_ratio=table_area_ratio,
        column_estimate=estimate_column_count(words, width),
        has_fonts=has_fonts,
        has_form_fields=page_has_form_widgets(page),
        page_class=classify_page(char_count, image_area_ratio),
    )
