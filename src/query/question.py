"""Reading a question: the part that only names its document.

Golden and real questions often say which document they mean: "According
to the CBE Annual Report 2023-24, ...", "(June 2017 file)", "in these
financial statements". The document is already chosen when the question is
answered, so these phrases are neither a period to look up (2023-24 is the
report's year, not the asked year) nor a name the evidence must repeat.
"""

from __future__ import annotations

import re

SOURCE_REFS = (
    re.compile(r"^\s*(?:according\s+to|in|from|per)\s+(?:the\s+)?[^,?]{3,160},\s*", re.IGNORECASE),
    re.compile(r",?\s*according\s+to\s+(?:the\s+|its\s+|this\s+)?[^,?]{3,160}(?=[,?]|$)", re.IGNORECASE),
    re.compile(r"\((?:[^()]*\b(?:file|report|edition|version)\b[^()]*)\)", re.IGNORECASE),
    re.compile(
        r"\b(?:in|of)\s+(?:these|this|the)\s+(?:financial\s+statements?|bulletin|report|document|procedure|survey|file)\b",
        re.IGNORECASE,
    ),
)


def without_source(question: str) -> str:
    """The question without the phrases that only name its document."""
    q = question or ""
    for pattern in SOURCE_REFS:
        q = pattern.sub(" ", q)
    return re.sub(r"\s{2,}", " ", q).strip()
