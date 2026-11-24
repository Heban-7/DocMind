"""FactTable: typed numbers from tables and text, and numeric questions answered in SQL.

    from src.facts.typed import facts_from_model
    from src.facts.query import FactQuery
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
