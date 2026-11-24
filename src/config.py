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

# --- Paths (resolved from this file, so they work from any working dir) -----
# src/config.py -> parents[1] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load the project's .env (if python-dotenv is available) so API keys and
# secrets can live in a file instead of the shell. The path is explicit so the
# same file is found whatever the working directory is. Tests set
# DOCMIND_SKIP_DOTENV=1 so they never pick up real keys or secrets.
if os.getenv("DOCMIND_SKIP_DOTENV", "").lower() not in {"1", "true", "yes"}:
    try:  # pragma: no cover - convenience only
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:  # pragma: no cover
        pass

DATA_DIR = PROJECT_ROOT / "data" / "data"
DEFAULT_SAMPLE_PDF = DATA_DIR / "sample.pdf"

# Root for local generated files: stored PDFs and document models
# (``storage/``, see src/storage/blobs.py). Never committed; override for tests
# and deployments. Documents, chunks, vectors, facts, page indexes, jobs, users
# and chat memory live in Postgres (DOCMIND_DATABASE_URL, see src/db/pool.py).
REFINERY_DIR = Path(os.getenv("DOCMIND_REFINERY_DIR", str(PROJECT_ROOT / ".refinery")))

# --- Phase 4 retrieval depth (how many LDUs / citations reach the answer) ---
# Semantic search previously defaulted to 5 and the synthesizer often kept only
# 3 citations -- too thin for "list the policies"-style questions. Raise floor.
SEMANTIC_TOP_K: int = int(os.getenv("DOCMIND_SEMANTIC_TOP_K", "7"))
PAGEINDEX_TOP_K: int = int(os.getenv("DOCMIND_PAGEINDEX_TOP_K", "5"))
MAX_CITATIONS: int = int(os.getenv("DOCMIND_MAX_CITATIONS", "8"))
MIN_CITATIONS: int = int(os.getenv("DOCMIND_MIN_CITATIONS", "5"))
EVIDENCE_EXCERPT_CHARS: int = int(os.getenv("DOCMIND_EVIDENCE_EXCERPT_CHARS", "700"))

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

# --- Extraction ---------------------------------------------------------------
# Compute device for Docling's models: "auto" uses CUDA (or Apple MPS) when
# available, else CPU, so the same code runs on a GPU laptop and on the
# CPU-only server. Lanes and threads: see src/document/device.py
# (DOCMIND_EXTRACT_LANES, DOCMIND_NUM_THREADS); pages per Docling call:
# DOCMIND_PAGE_BATCH; TableFormer mode: DOCMIND_V2_TABLE_MODE.
EXTRACTION_DEVICE: str = os.getenv("DOCMIND_DEVICE", "auto")  # auto|cuda|mps|cpu

# --- OCR (Tesseract, Amharic-aware) ---------------------------------------------
# Scanned pages are read by the Tesseract CLI with these languages (ISO 639-2).
# Default suits Ethiopian documents. Override: DOCMIND_OCR_LANGS="amh+eng".
# On 2 CPU cores English-only was just 6% faster, so Amharic stays on.
OCR_LANGUAGES: list[str] = os.getenv("DOCMIND_OCR_LANGS", "amh+eng").split("+")


# --- LLM and vision settings ---------------------------------------------------
class VisionConfig:
    """Provider credentials and models; the vision fallback for unreadable pages.

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

    # Budget guard: hard ceiling on estimated vision spend per document.
    BUDGET_USD: float = 1.00


# --- Embeddings (Phase 4 vector search) -------------------------------------
class EmbeddingConfig:
    """OpenAI embedding settings for chunk ingestion + semantic search.

    The ``chunks.embedding`` column is vector(1536), the native size of
    text-embedding-3-small; a model with another size needs a migration.

    Uses the same OPENAI_API_KEY as the LLM layer. Default model is the
    current cost-efficient OpenAI embedding model (text-embedding-3-small).
    """

    PROVIDER: str = os.getenv("DOCMIND_EMBEDDING_PROVIDER", "openai")
    MODEL: str = os.getenv("DOCMIND_EMBEDDING_MODEL", "text-embedding-3-small")
    # text-embedding-3-small native dim is 1536; smaller dims are cheaper to store.
    DIMENSIONS: int | None = (
        int(os.environ["DOCMIND_EMBEDDING_DIMS"])
        if os.getenv("DOCMIND_EMBEDDING_DIMS")
        else None
    )
    # How many LDU texts to embed per OpenAI request (batch for cost/latency).
    BATCH_SIZE: int = int(os.getenv("DOCMIND_EMBEDDING_BATCH", "64"))


# --- Domain hint ------------------------------------------------------------------
class Thresholds:
    """Tunable decision boundaries."""

    # DOMAIN: minimum confidence (share of keyword hits) for a specific domain;
    # below this we fall back to "general".
    DOMAIN_MIN_CONFIDENCE: float = 0.34
