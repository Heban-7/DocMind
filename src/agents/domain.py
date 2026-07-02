"""
Domain-hint classification, built as a swappable strategy.

We define a `DomainClassifier` Protocol (the contract) and ship THREE
implementations that all satisfy it:
  * KeywordDomainClassifier  -- fast, offline, English-only word counting.
  * LlmDomainClassifier      -- an LLM reads the title/snippet and returns a
    structured domain guess (understands Amharic, uses meaning not just words).
  * FallbackDomainClassifier -- LLM-first, then keyword when the LLM is
    unavailable/errors/low-confidence, so it is NEVER worse than keywords and
    still works fully offline.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol, runtime_checkable

from src.config import Thresholds
from src.models.document_profile import DomainHint

logger = logging.getLogger("docmind.domain")


@runtime_checkable
class DomainClassifier(Protocol):
    """Anything that can turn document text into a (domain, confidence) guess."""

    def classify(self, text: str) -> tuple[DomainHint, float]: ...


# Indicative vocabulary per domain. Deliberately small and readable; this is a
# starting point that Phase 2 can externalize/expand.
_DOMAIN_KEYWORDS: dict[DomainHint, set[str]] = {
    DomainHint.FINANCIAL: {
        "revenue", "balance", "income", "statement", "assets", "liabilities",
        "profit", "loss", "fiscal", "tax", "audit", "equity", "cash", "expenditure",
        "budget", "financial", "depreciation", "dividend", "capital", "expense",
    },
    DomainHint.LEGAL: {
        "agreement", "plaintiff", "defendant", "court", "clause", "hereby",
        "whereas", "jurisdiction", "law", "regulation", "act", "statute",
        "liability", "indemnity", "contract", "party", "tribunal", "appeal",
    },
    DomainHint.TECHNICAL: {
        "assessment", "implementation", "system", "architecture", "methodology",
        "specification", "vulnerability", "procedure", "framework", "protocol",
        "deployment", "infrastructure", "configuration", "module", "interface",
    },
    DomainHint.MEDICAL: {
        "patient", "diagnosis", "treatment", "clinical", "dose", "dosage",
        "symptom", "therapy", "disease", "medical", "pharmaceutical", "physician",
        "hospital", "vaccine", "infection",
    },
}


class KeywordDomainClassifier:
    """Counts whole-word keyword hits per domain and picks the strongest."""

    def __init__(self, min_confidence: float = Thresholds.DOMAIN_MIN_CONFIDENCE):
        self._min_confidence = min_confidence

    def classify(self, text: str) -> tuple[DomainHint, float]:
        lowered = text.lower()

        scores: dict[DomainHint, int] = {}
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            hits = 0
            for kw in keywords:
                # \b ensures whole-word matches ("tax", not "taxonomy").
                hits += len(re.findall(rf"\b{re.escape(kw)}\b", lowered))
            scores[domain] = hits

        total_hits = sum(scores.values())
        if total_hits == 0:
            return (DomainHint.GENERAL, 0.0)

        best_domain = max(scores, key=scores.get)
        confidence = scores[best_domain] / total_hits

        if confidence < self._min_confidence:
            # Signals are too diffuse to commit to a specialty.
            return (DomainHint.GENERAL, confidence)
        return (best_domain, confidence)


# --- LLM-based classifier ---------------------------------------------------
_ALLOWED_DOMAINS = [d.value for d in DomainHint]

_DOMAIN_PROMPT = (
    "You classify a document into exactly ONE domain based on the excerpt below.\n"
    f"Allowed domains: {', '.join(_ALLOWED_DOMAINS)}.\n"
    "The text may be in any language (e.g. Amharic); classify by meaning.\n"
    "Respond with STRICT JSON only, no prose:\n"
    '{"domain": "<one of the allowed>", "confidence": <0.0-1.0>}\n\n'
    "Document excerpt:\n"
)

# How much of the sampled text to send (keeps the call cheap: title + opening).
_SNIPPET_CHARS = 1500


def _parse_domain_json(raw: str) -> tuple[DomainHint, float] | None:
    """Leniently parse the model's JSON into (DomainHint, confidence)."""
    text = raw.strip()
    if not text:
        return None
    # Strip code fences and isolate the first {...} block if wrapped in prose.
    if "```" in text:
        text = text.replace("```json", "```").split("```")[1].strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        domain = DomainHint(str(data["domain"]).strip().lower())
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        return (domain, confidence)
    except (ValueError, KeyError, TypeError):
        return None


class LlmDomainClassifier:
    """Asks an LLM for a structured (domain, confidence) guess."""

    def __init__(self, client=None, model: str | None = None):
        # Lazy import so the triage module has no hard dependency on the LLM
        # stack when running fully offline.
        if client is None:
            from src.llm.factory import get_client, get_text_client

            client = get_client(model=model) if model else get_text_client()
        self._client = client

    @property
    def available(self) -> bool:
        return self._client is not None

    def classify(self, text: str) -> tuple[DomainHint, float]:
        if self._client is None:
            return (DomainHint.GENERAL, 0.0)
        snippet = text[:_SNIPPET_CHARS]
        try:
            result = self._client.complete(
                _DOMAIN_PROMPT + snippet,
                response_format="json",
                temperature=0.0,
                max_tokens=100,
            )
        except Exception as exc:  # network/provider error -> caller can fall back
            logger.warning("LLM domain classification failed: %s", exc)
            raise
        parsed = _parse_domain_json(result.text)
        if parsed is None:
            logger.warning("LLM domain output unparseable: %r", result.text[:120])
            return (DomainHint.GENERAL, 0.0)
        return parsed


class FallbackDomainClassifier:
    """LLM-first, keyword-fallback classifier.

    Uses the primary (LLM) classifier when it is available and confident; falls
    back to the keyword classifier on error, low confidence, or a GENERAL/0.0
    result. This guarantees behavior is never worse than keywords alone.
    """

    def __init__(
        self,
        primary: DomainClassifier,
        fallback: DomainClassifier,
        min_confidence: float = Thresholds.DOMAIN_MIN_CONFIDENCE,
    ):
        self._primary = primary
        self._fallback = fallback
        self._min_confidence = min_confidence

    def classify(self, text: str) -> tuple[DomainHint, float]:
        try:
            domain, confidence = self._primary.classify(text)
            if domain is not DomainHint.GENERAL and confidence >= self._min_confidence:
                return (domain, confidence)
        except Exception:
            pass  # fall through to keywords
        return self._fallback.classify(text)


def build_default_domain_classifier() -> DomainClassifier:
    """Best available classifier: LLM-with-keyword-fallback if a key exists,
    otherwise keyword-only (fully offline)."""
    keyword = KeywordDomainClassifier()
    try:
        llm = LlmDomainClassifier()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not init LLM domain classifier: %s", exc)
        return keyword
    if llm.available:
        return FallbackDomainClassifier(primary=llm, fallback=keyword)
    return keyword
