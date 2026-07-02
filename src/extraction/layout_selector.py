"""
Strategy B selector -- Docling vs. MinerU.

Both are layout-aware engines with complementary strengths:
  * Docling  -> enterprise layouts, efficient tables, CPU-friendly (default).
  * MinerU   -> scientific/multi-column docs and especially math formulas.

We route math/scientific-heavy documents to MinerU (when it is installed) and
everything else to Docling. The decision uses the `avg_math_symbol_ratio` signal
that Triage already measured.
"""

from __future__ import annotations

from src.config import Thresholds
from src.extraction.base import BaseExtractionEngine
from src.extraction.layout_docling import DoclingLayoutEngine
from src.extraction.layout_mineru import MinerULayoutEngine
from src.models.document_profile import DocumentProfile


class LayoutStrategySelector:
    """Chooses the best-fit layout engine for a given DocumentProfile."""

    def select(self, profile: DocumentProfile) -> BaseExtractionEngine:
        math_heavy = (
            profile.signals.avg_math_symbol_ratio
            >= Thresholds.MATH_HEAVY_SYMBOL_RATIO
        )
        if math_heavy and MinerULayoutEngine.is_available():
            return MinerULayoutEngine()
        # Default: Docling (also the graceful fallback if MinerU is unavailable).
        return DoclingLayoutEngine()
