"""Cross-encoder reranking of retrieval candidates.

The default model, ``cross-encoder/ms-marco-MiniLM-L6-v2`` (Apache-2.0,
22M parameters, ~90 MB), reads the question and each candidate together
and scores how well the candidate answers it; on two CPU cores twenty
candidates take a fraction of a second. It is English-only, so questions
written in Ethiopic script keep the fused order.

    DOCMIND_RERANKER=off              # skip reranking
    DOCMIND_RERANKER=<hf model id>    # another cross-encoder
    DOCMIND_MODELS_DIR=...            # where models are stored (default ~/.cache/docmind/models)
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
from pathlib import Path

logger = logging.getLogger("docmind.rerank")

# Off by default: on the golden set this model moved the right page up a little
# (hit@5 76.9% -> 77.8%) but put fewer answer-bearing chunks in the top 5
# (81.2% -> 76.9%) and added ~3.6 s per question on CPU. It was trained on web
# passages, not tables of figures. Opt in with DOCMIND_RERANKER=<model id>.
DEFAULT_MODEL = "off"
SUGGESTED_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
_ETHIOPIC = re.compile(r"[ሀ-፿]")
_lock = threading.Lock()
_loaded: dict[str, tuple[object, object]] = {}
_failed: set[str] = set()


def model_name() -> str | None:
    name = os.getenv("DOCMIND_RERANKER", DEFAULT_MODEL).strip()
    return None if name.lower() in {"", "off", "none", "0", "false"} else name


def models_dir() -> Path:
    """Shared by every run and account on the machine (default ~/.cache/docmind/models)."""
    return Path(os.getenv("DOCMIND_MODELS_DIR") or (Path.home() / ".cache" / "docmind" / "models"))


def _load(name: str):
    """Tokenizer and model, downloaded once into the models folder (no symlinks, so it works on Windows)."""
    with _lock:
        if name in _loaded:
            return _loaded[name]
        if name in _failed:
            return None
        try:
            import torch
            from huggingface_hub import snapshot_download
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            local = models_dir() / name.split("/")[-1]
            if not (local / "config.json").exists():
                snapshot_download(
                    name, local_dir=str(local), allow_patterns=["*.json", "*.txt", "*.safetensors"]
                )
            tok = AutoTokenizer.from_pretrained(str(local))
            model = AutoModelForSequenceClassification.from_pretrained(str(local))
            model.eval()
            torch.set_grad_enabled(False)
            _loaded[name] = (tok, model)
            return _loaded[name]
        except Exception as exc:  # no network on first use, etc.: fall back to fused order
            logger.warning("reranker %s unavailable: %s", name, exc)
            _failed.add(name)
            return None


def available() -> bool:
    name = model_name()
    return bool(name) and _load(name) is not None


def scores(question: str, passages: list[str], *, max_chars: int = 1600) -> list[float] | None:
    """Relevance in (0, 1) for each passage, or None when reranking is off or impossible."""
    name = model_name()
    if not name or not passages or _ETHIOPIC.search(question or ""):
        return None
    loaded = _load(name)
    if loaded is None:
        return None
    tok, model = loaded
    import torch

    with torch.inference_mode():
        batch = tok(
            [question] * len(passages),
            [p[:max_chars] for p in passages],
            padding=True,
            truncation=True,
            max_length=384,
            return_tensors="pt",
        )
        logits = model(**batch).logits.view(-1).tolist()
    return [1.0 / (1.0 + math.exp(-x)) for x in logits]
