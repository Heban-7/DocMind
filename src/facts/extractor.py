"""Facts from chunks of Markdown, for callers that have no document model.

The ingest pipeline reads facts from the structured document model
(``src.facts.typed.facts_from_model``), where every number keeps its page,
cell and box. This module applies the same typed reading to plain chunks
(the offline demo and unit tests): Markdown table rows become table facts,
other text becomes text facts, with the chunk's first page as the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.chunking.models import DocumentChunk
from src.document.model import Block, BlockType, Page, PageQuality
from src.facts.models import FactRecord
from src.facts.typed import _facts_from_markdown, _markdown_grid, facts_from_text, normalize_period

if TYPE_CHECKING:  # src.stores imports src.facts.models; avoid the cycle at runtime
    from src.stores.base import FactStore


def _page_for(chunk: DocumentChunk) -> Page:
    number = chunk.metadata.page_numbers[0] if chunk.metadata.page_numbers else 1
    return Page(number=number, width=0, height=0, quality=PageQuality(engine="text_layer", confidence=1.0))


def _with_chunk(facts: list[FactRecord], chunk: DocumentChunk) -> list[FactRecord]:
    section = chunk.metadata.parent_hierarchy[-1] if chunk.metadata.parent_hierarchy else ""
    return [
        f.model_copy(
            update={
                "content_hash": chunk.metadata.content_hash,
                "chunk_id": chunk.id,
                "table_title": f.table_title or (section if f.source == "table" else ""),
                "period_key": normalize_period(f.period or f.column_label),
            }
        )
        for f in facts
    ]


def extract_facts_from_table(chunk: DocumentChunk, *, doc_id: str, document_name: str = "") -> list[FactRecord]:
    """Numeric cells of the Markdown tables in a chunk."""
    page = _page_for(chunk)
    if not _markdown_grid(chunk.text):
        return []
    block = Block(block_id=f"{chunk.id}-t", type=BlockType.TEXT, text=chunk.text)
    return _with_chunk(_facts_from_markdown(page, block, doc_id=doc_id, document_name=document_name, index=0), chunk)


def extract_facts_from_prose(chunk: DocumentChunk, *, doc_id: str, document_name: str = "") -> list[FactRecord]:
    """Numbers in the chunk's running text (table lines left out)."""
    page = _page_for(chunk)
    text = "\n".join(line for line in chunk.text.splitlines() if not line.strip().startswith("|"))
    block = Block(block_id=f"{chunk.id}-p", type=BlockType.TEXT, text=text)
    return _with_chunk(facts_from_text(page, block, doc_id=doc_id, document_name=document_name), chunk)


def extract_facts_from_chunk(chunk: DocumentChunk, *, doc_id: str, document_name: str = "") -> list[FactRecord]:
    return extract_facts_from_table(chunk, doc_id=doc_id, document_name=document_name) + extract_facts_from_prose(
        chunk, doc_id=doc_id, document_name=document_name
    )


@dataclass
class FactExtractResult:
    doc_id: str
    facts_written: int
    facts_total_for_doc: int


def extract_and_store(
    chunks: list[DocumentChunk],
    *,
    doc_id: str,
    store: FactStore,
    document_name: str = "",
) -> FactExtractResult:
    """Extract facts from chunks and replace the document's facts in ``store``."""
    facts: list[FactRecord] = []
    seen: set[tuple] = set()
    for chunk in chunks:
        for f in extract_facts_from_chunk(chunk, doc_id=doc_id, document_name=document_name):
            key = (f.metric.lower(), f.value_text, f.column_label.lower(), f.page_number)
            if key not in seen:
                seen.add(key)
                facts.append(f)
    written = store.replace_doc_facts(doc_id, facts)
    return FactExtractResult(doc_id=doc_id, facts_written=written, facts_total_for_doc=store.count(doc_id))
