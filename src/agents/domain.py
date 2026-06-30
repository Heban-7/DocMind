"""
Domain-hint classification, built as a swappable strategy.

Requirement: "simple keyword-based approach is acceptable, but implement it as
a pluggable strategy so VLM classification can be swapped in." So we define a
`DomainClassifier` Protocol (the contract) and ship one keyword-based
implementation. A future `VlmDomainClassifier` only needs the same `.classify`
method to drop straight into the TriageAgent.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from src.config import Thresholds
from src.models.document_profile import DomainHint


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
