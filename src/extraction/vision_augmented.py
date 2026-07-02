"""
Strategy C -- Vision-Augmented (Cost: High).

The real VLM tier, exactly as the architecture intends: render each page to an
image and ask a multimodal model to transcribe it into clean Markdown. The
provider is whatever you plugged in (OpenRouter / OpenAI / Gemini) -- resolved
by the LLM factory.

Two production safeguards:
  * BudgetGuard -- a hard per-document spend cap (never burn the budget).
  * OCR fallback -- if NO LLM credential is available, fall back to local
    Docling OCR so the pipeline still degrades gracefully offline.

The router only selects this tier when Triage flags `needs_vision_model`.
"""

from __future__ import annotations

from src.config import VisionConfig
from src.extraction._docling_support import convert_to_markdown
from src.extraction.base import BaseExtractionEngine
from src.extraction.page_render import render_pages_to_png
from src.llm.budget import BudgetExceededError, BudgetGuard
from src.llm.factory import build_vision_client

# Sentinel so callers can inject `client=None` (force OCR) vs. leave it to auto.
_AUTO = object()

_EXTRACTION_PROMPT = (
    "You are a precise document transcription engine. Transcribe this page "
    "into clean GitHub-Flavored Markdown. Preserve structure: use # headings, "
    "render tables as Markdown tables with correct rows/columns, and keep lists. "
    "Output ONLY the transcribed content -- no commentary, no code fences."
)


class VisionAugmentedEngine(BaseExtractionEngine):
    """VLM transcription for scanned / visually complex documents."""

    name = "vision_augmented"

    def __init__(
        self,
        client=_AUTO,
        max_pages: int = VisionConfig.MAX_PAGES,
        dpi: int = VisionConfig.RENDER_DPI,
        budget_usd: float = VisionConfig.BUDGET_USD,
        allow_ocr_fallback: bool = VisionConfig.ALLOW_OCR_FALLBACK,
        ocr_max_pages: int | None = VisionConfig.OCR_FALLBACK_MAX_PAGES,
    ):
        # `_AUTO` -> resolve from environment; an explicit value (incl. None)
        # is honored so tests can inject a fake client or force the fallback.
        self.client = build_vision_client() if client is _AUTO else client
        self.max_pages = max_pages  # PAID VLM page budget (cost control)
        self.dpi = dpi
        self.budget_usd = budget_usd
        self.allow_ocr_fallback = allow_ocr_fallback
        # Local OCR is free, so its page budget is separate (whole doc by default).
        self.ocr_max_pages = ocr_max_pages

    def extract(self, file_path: str) -> str:
        if self.client is None:
            if not self.allow_ocr_fallback:
                raise RuntimeError(
                    "No vision LLM credential found and OCR fallback is disabled. "
                    "Set OPENROUTER_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY."
                )
            return self._extract_with_ocr(file_path)
        return self._extract_with_vlm(file_path)

    def _extract_with_vlm(self, file_path: str) -> str:
        images = render_pages_to_png(file_path, self.max_pages, self.dpi)
        guard = BudgetGuard(self.budget_usd)

        parts: list[str] = []
        for page_number, image in enumerate(images, start=1):
            try:
                guard.assert_can_spend()
            except BudgetExceededError:
                parts.append(
                    f"<!-- budget cap ${self.budget_usd:.2f} reached; "
                    f"stopped before page {page_number} -->"
                )
                break
            result = self.client.analyze_image(image, _EXTRACTION_PROMPT)
            guard.record(result.cost_usd)
            parts.append(f"<!-- page {page_number} -->\n{result.text.strip()}")

        return "\n\n".join(parts).strip()

    def _extract_with_ocr(self, file_path: str) -> str:
        """Offline fallback: Docling with OCR enabled (whole document by default)."""
        return convert_to_markdown(
            file_path, do_ocr=True, max_pages=self.ocr_max_pages
        )
