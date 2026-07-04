"""
Central configuration for the DocMind Refinery.

Everything that is "tunable" or "environment-specific" lives here so that no
other module hardcodes a path or a magic number. In Phase 2 the THRESHOLDS
below will be externalized to `rubric/extraction_rules.yaml`; for Phase 1 we
keep them as named, justified constants in one obvious place.
"""

from __future__ import annotations

import os
from pathlib import Path

# Load a local .env file if python-dotenv is available, so API keys can be set
# in a file instead of the shell. Optional: absence is fine.
try:  # pragma: no cover - convenience only
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

# --- Paths (resolved from this file, so they work from any working dir) -----
# src/config.py -> parents[1] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "data"
DEFAULT_SAMPLE_PDF = DATA_DIR / "sample.pdf"

REFINERY_DIR = PROJECT_ROOT / ".refinery"
PROFILES_DIR = REFINERY_DIR / "profiles"
EXTRACTIONS_DIR = REFINERY_DIR / "extractions"
CHUNKS_DIR = REFINERY_DIR / "chunks"

# --- Chunking (Phase 3) -----------------------------------------------------
# Soft target and hard ceiling (in words) for a Logical Document Unit. The
# chunker aims for ~target and never splits atomic structures (tables/code);
# only prose/lists beyond max are split, on sentence/line boundaries.
CHUNK_TARGET_WORDS: int = int(os.getenv("DOCMIND_CHUNK_TARGET_WORDS", "450"))
CHUNK_MAX_WORDS: int = int(os.getenv("DOCMIND_CHUNK_MAX_WORDS", "800"))

# The model registry (friendly name -> provider/slug/capabilities/pricing).
MODEL_REGISTRY_PATH = Path(
    os.getenv("DOCMIND_MODEL_REGISTRY", str(PROJECT_ROOT / "rubric" / "models.yaml"))
)

# Upper bound on pages sent to the heavy Docling-based engines (layout/vision).
# Now that extraction runs in small page batches (see DOCLING_PAGE_BATCH), peak
# RAM is just one batch at a time, so we can safely process the WHOLE document.
# None = no limit (entire document). Set an integer only if you want to cap very
# large PDFs for speed.
EXTRACTION_MAX_PAGES: int | None = None

# --- Extraction acceleration (production-portable) --------------------------
# Compute device for Docling's ML models + EasyOCR. "auto" resolves to CUDA (or
# Apple MPS) when available, else CPU -- so the SAME code is fast on a GPU box
# and still correct on a CPU-only production server. Override: DOCMIND_DEVICE.
EXTRACTION_DEVICE: str = os.getenv("DOCMIND_DEVICE", "auto")  # auto|cuda|mps|cpu
# CPU thread count for the native (non-GPU) portions of the pipeline.
DOCLING_NUM_THREADS: int = int(os.getenv("DOCMIND_NUM_THREADS", "8"))

# How many pages Docling converts per internal call. Docling rasterizes pages
# into large bitmaps; doing a whole range at once can exhaust RAM
# (std::bad_alloc). Batching caps PEAK memory and releases it between batches.
# The batch is DEVICE-AWARE: GPUs can handle several pages at once (faster),
# while CPU-only hosts stay at 1 to remain memory-safe in production.
DOCLING_PAGE_BATCH_GPU: int = int(os.getenv("DOCMIND_PAGE_BATCH_GPU", "8"))
DOCLING_PAGE_BATCH_CPU: int = int(os.getenv("DOCMIND_PAGE_BATCH_CPU", "2"))

# TableFormer mode: "fast" (lighter, lower memory) or "accurate" (heavier).
DOCLING_TABLE_MODE: str = os.getenv("DOCMIND_TABLE_MODE", "fast")

# --- OCR engine (Amharic-aware) ---------------------------------------------
# EasyOCR CANNOT read Amharic/Ethiopic script; Tesseract (with the `amh` data)
# can. "auto" uses Tesseract when its CLI is installed (needed for Amharic),
# otherwise EasyOCR. Override: DOCMIND_OCR_ENGINE.
OCR_ENGINE: str = os.getenv("DOCMIND_OCR_ENGINE", "auto")  # auto|tesseract|easyocr
# OCR languages (Tesseract ISO 639-2 codes). Default suits Ethiopian docs
# (Amharic + English). Override: DOCMIND_OCR_LANGS="amh+eng".
OCR_LANGUAGES: list[str] = os.getenv("DOCMIND_OCR_LANGS", "amh+eng").split("+")

# Bumped whenever the triage heuristics change, so stored profiles are traceable
# back to the logic that produced them.
TRIAGE_VERSION = "1.1.0"


# --- Vision (Strategy C) settings -------------------------------------------
class VisionConfig:
    """Settings for the real VLM tier and its OCR fallback.

    Provider is chosen by whatever credential you plug in (see src/llm/factory).
    You can also force a provider/model via the LLM_PROVIDER / LLM_MODEL env vars.
    """

    # Explicit overrides (optional). If unset, the factory auto-detects.
    # PROVIDER forces a provider; MODEL forces a model (friendly name or slug).
    PROVIDER: str | None = os.getenv("LLM_PROVIDER")  # openrouter|openai|gemini|groq
    MODEL: str | None = os.getenv("LLM_MODEL")
    # Separate default for cheap TEXT tasks (e.g. domain classification). If
    # unset, the registry's `defaults.text` is used.
    TEXT_MODEL: str | None = os.getenv("LLM_TEXT_MODEL")

    # Credentials are read from the environment (never hardcoded).
    OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or os.getenv(
        "GOOGLE_API_KEY"
    )

    # Sensible per-provider default models (used when MODEL is unset). Values are
    # friendly names resolved through the model registry (rubric/models.yaml).
    DEFAULT_MODELS: dict[str, str] = {
        "openrouter": "or-gemini-flash",
        "openai": "gpt-4o-mini",
        "gemini": "gemini-flash",
        "groq": "groq-llama-vision",
    }

    # How many leading pages to send to the PAID VLM, and at what resolution.
    # This caps cost; the BudgetGuard is the second, hard safety net.
    MAX_PAGES: int = 5
    RENDER_DPI: int = 150

    # Budget guard: hard ceiling on estimated spend per single document.
    BUDGET_USD: float = 1.00

    # If no LLM credential is available, fall back to local Docling OCR.
    ALLOW_OCR_FALLBACK: bool = True
    # OCR is local and free, so the fallback processes the WHOLE document by
    # default (None). It is NOT limited by MAX_PAGES (which exists for VLM cost).
    OCR_FALLBACK_MAX_PAGES: int | None = None


# --- Triage heuristic thresholds --------------------------------------------
# These are the empirically-grounded "dials" of the Triage Agent. Each is a
# plain number with a justification, ready to be moved into a YAML file later.
class Thresholds:
    """Tunable decision boundaries for the heuristic Triage Agent."""

    # Triage samples a representative subset of pages (cheap pdfplumber reads).
    # The sample size is ADAPTIVE: ~5% of pages, clamped between a floor and a
    # ceiling, so a 600-page report gets more coverage than a 20-page one.
    SAMPLE_MIN_PAGES: int = 12
    SAMPLE_MAX_PAGES: int = 24
    SAMPLE_FRACTION: float = 0.05

    # LAYOUT SELECTOR: average share of math/scientific symbols above which we
    # prefer MinerU (formula/equation strength) over Docling for Strategy B.
    MATH_HEAVY_SYMBOL_RATIO: float = 0.02

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
