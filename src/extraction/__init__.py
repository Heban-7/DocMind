"""Phase 2: the multi-strategy extraction engines and their router.

    from src.extraction.router import ExtractionRouter
"""

from src.extraction.base import BaseExtractionEngine
from src.extraction.fast_text import FastTextEngine
from src.extraction.layout_docling import DoclingLayoutEngine
from src.extraction.layout_mineru import MinerULayoutEngine
from src.extraction.layout_selector import LayoutStrategySelector
from src.extraction.router import ExtractionRouter
from src.extraction.vision_augmented import VisionAugmentedEngine

__all__ = [
    "BaseExtractionEngine",
    "FastTextEngine",
    "DoclingLayoutEngine",
    "MinerULayoutEngine",
    "LayoutStrategySelector",
    "VisionAugmentedEngine",
    "ExtractionRouter",
]
