"""FactTable: numerical facts extracted from LDUs into SQLite.

    from src.facts import FactStore, extract_and_store, extract_facts_from_chunk
"""

from src.facts.extractor import (
    FactExtractResult,
    extract_and_store,
    extract_and_store_from_chunks_file,
    extract_facts_from_chunk,
    extract_facts_from_prose,
    extract_facts_from_table,
)
from src.facts.models import FactRecord
from src.facts.store import FactStore

__all__ = [
    "FactRecord",
    "FactStore",
    "FactExtractResult",
    "extract_facts_from_chunk",
    "extract_facts_from_prose",
    "extract_facts_from_table",
    "extract_and_store",
    "extract_and_store_from_chunks_file",
]
