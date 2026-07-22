"""
PageIndex contracts -- a navigable "smart table of contents" over a document.

Each node is a section with page span, child sections, data-type hints, and an
optional short summary. The Query Agent's `pageindex_navigate` tool walks this
tree to find relevant sections *before* (or instead of) vector search.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class SectionNode(BaseModel):
    """One node in the PageIndex tree (a document section / subsection)."""

    model_config = ConfigDict(frozen=True)

    title: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    path: list[str] = Field(
        default_factory=list,
        description="Full breadcrumb including this title, e.g. "
        "['Chapter 1', 'Section A'].",
    )
    summary: str = Field(
        default="",
        description="2-3 sentence summary (LLM or extractive fallback).",
    )
    data_types_present: list[str] = Field(
        default_factory=list,
        description="chunk types seen under this section: table, prose, list, ...",
    )
    chunk_ids: list[str] = Field(
        default_factory=list,
        description="LDU ids whose parent_hierarchy equals this path.",
    )
    key_entities: list[str] = Field(
        default_factory=list,
        description="Optional named entities (filled later / by LLM).",
    )
    children: list[SectionNode] = Field(default_factory=list)


class PageIndex(BaseModel):
    """The full hierarchical index for one ingested document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str
    source_filename: str = ""
    roots: list[SectionNode] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def iter_nodes(self) -> list[SectionNode]:
        """Depth-first flattening of every section node."""
        out: list[SectionNode] = []

        def walk(nodes: list[SectionNode]) -> None:
            for node in nodes:
                out.append(node)
                if node.children:
                    walk(list(node.children))

        walk(list(self.roots))
        return out
