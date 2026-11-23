"""FactTable: numerical facts extracted from chunks.

    from src.facts import extract_and_store, extract_facts_from_chunk
"""

from src.facts.extractor import (
    FactExtractResult,
    extract_and_store,
    extract_facts_from_chunk,
    extract_facts_from_prose,
    extract_facts_from_table,
)
from src.facts.models import FactRecord

__all__ = [
    "FactRecord",
    "FactExtractResult",
    "extract_facts_from_chunk",
    "extract_facts_from_prose",
    "extract_facts_from_table",
    "extract_and_store",
]
