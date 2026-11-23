"""
The Extraction Router -- the switchboard.

It reads the Triage Agent's verdict (`profile.strategy_tier`) and returns the
single correct engine for that document:

    fast_text_sufficient -> FastTextEngine
    needs_layout_model   -> Docling OR MinerU (chosen by LayoutStrategySelector)
    needs_vision_model   -> VisionAugmentedEngine (real VLM, OCR fallback)

The rest of the pipeline just asks the router for "the right engine" and calls
`.extract()` -- it never needs to know the mapping itself.
"""

from __future__ import annotations

import os

from src.extraction.base import BaseExtractionEngine
from src.extraction.fast_text import FastTextEngine
from src.extraction.layout_selector import LayoutStrategySelector
from src.extraction.vision_augmented import VisionAugmentedEngine
from src.models.document_profile import DocumentProfile, ExtractionCost


class ExtractionRouter:
    """Selects and instantiates the extraction engine for a DocumentProfile."""

    def __init__(self):
        self._layout_selector = LayoutStrategySelector()

    def get_engine(self, profile: DocumentProfile) -> BaseExtractionEngine:
        """Return the extraction engine for this document.

        V2 (default) routes every page on its own inside one engine, so the
        document-level tier no longer decides what is read. Set
        ``DOCMIND_EXTRACTOR=v1`` to get the original per-document switch.
        """
        if os.getenv("DOCMIND_EXTRACTOR", "v2").lower() != "v1":
            from src.extraction.structured import StructuredExtractionEngine

            return StructuredExtractionEngine()
        tier = profile.strategy_tier

        if tier == ExtractionCost.FAST_TEXT_SUFFICIENT:
            return FastTextEngine()
        if tier == ExtractionCost.NEEDS_LAYOUT_MODEL:
            # Sub-decision: Docling vs MinerU, based on document signals.
            return self._layout_selector.select(profile)
        if tier == ExtractionCost.NEEDS_VISION_MODEL:
            return VisionAugmentedEngine()

        raise ValueError(f"No extraction engine registered for tier '{tier}'.")
