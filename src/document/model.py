"""Typed document model shared by every extraction engine.

Coordinates are PDF points with a TOP-LEFT origin: ``x0`` and ``x1`` from the
left edge, ``top`` and ``bottom`` from the top edge. Engines that report a
bottom-left origin (Docling's item provenance) are converted on the way in.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class BBox(BaseModel):
    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def union(self, other: "BBox") -> "BBox":
        return BBox(
            x0=min(self.x0, other.x0),
            top=min(self.top, other.top),
            x1=max(self.x1, other.x1),
            bottom=max(self.bottom, other.bottom),
        )

    def contains_point(self, x: float, y: float, slack: float = 1.0) -> bool:
        return self.x0 - slack <= x <= self.x1 + slack and self.top - slack <= y <= self.bottom + slack

    def as_list(self) -> list[float]:
        return [round(self.x0, 2), round(self.top, 2), round(self.x1, 2), round(self.bottom, 2)]

    @classmethod
    def from_bottom_left(cls, left: float, top: float, right: float, bottom: float, page_height: float) -> "BBox":
        """Convert a bottom-left-origin box (``top`` > ``bottom``) to top-left."""
        return cls(x0=left, top=page_height - top, x1=right, bottom=page_height - bottom)


class BlockType(str, Enum):
    TITLE = "title"
    HEADING = "heading"
    TEXT = "text"
    LIST_ITEM = "list_item"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    FIGURE = "figure"
    TABLE = "table"  # marks where a table sits in reading order; text = its table_id
    PAGE_HEADER = "page_header"  # running headers and footers: kept, but not body text
    PAGE_FOOTER = "page_footer"


class Block(BaseModel):
    block_id: str = Field(description="Stable id: p<page>-b<index>")
    type: BlockType
    text: str
    bbox: BBox | None = None
    level: int | None = Field(default=None, description="Heading level, 1 = top")
    confidence: float | None = Field(default=None, description="OCR word confidence 0-1, when OCR read it")


class TableCell(BaseModel):
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    text: str
    bbox: BBox | None = None
    is_header: bool = False
    text_source: str = Field(default="engine", description="engine | text_layer | ocr")


class Table(BaseModel):
    table_id: str = Field(description="Stable id: p<page>-t<index>")
    bbox: BBox | None = None
    n_rows: int
    n_cols: int
    cells: list[TableCell]
    caption: str = ""
    continued_from: str | None = Field(default=None, description="table_id on the previous page this continues")

    def grid(self) -> list[list[str]]:
        rows = [["" for _ in range(self.n_cols)] for _ in range(self.n_rows)]
        for c in self.cells:
            if 0 <= c.row < self.n_rows and 0 <= c.col < self.n_cols:
                rows[c.row][c.col] = c.text
        return rows

    def header_rows(self) -> int:
        rows = {c.row for c in self.cells if c.is_header}
        n = 0
        while n in rows:
            n += 1
        return n


class PageQuality(BaseModel):
    """Why the page was read the way it was, and how far to trust it."""

    engine: str = Field(description="text_layer | docling | ocr | vision | none")
    confidence: float = Field(ge=0.0, le=1.0)
    checks: dict[str, float | int | bool | str] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list, description="Problems a person should see")
    attempts: list[str] = Field(default_factory=list, description="Engines tried, in order")
    seconds: float = 0.0
    cost_usd: float = 0.0
    needs_review: bool = False


class Page(BaseModel):
    number: int = Field(ge=1, description="1-indexed physical page")
    width: float
    height: float
    blocks: list[Block] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    quality: PageQuality
    script: str = Field(default="latin", description="latin | ethiopic | mixed | none")

    def body_text(self) -> str:
        return "\n".join(
            b.text
            for b in self.blocks
            if b.type not in (BlockType.PAGE_HEADER, BlockType.PAGE_FOOTER, BlockType.TABLE)
        )


class DocumentModel(BaseModel):
    schema_version: str = "1"
    doc_id: str
    file_name: str
    sha256: str
    page_count: int
    pages: list[Page]
    seconds: float = 0.0
    cost_usd: float = 0.0
    extractor: str = "docmind-v2"

    def page(self, number: int) -> Page:
        return self.pages[number - 1]

    def ledger(self) -> list[dict]:
        """One row per page: the extraction ledger the spec asks for."""
        return [
            {
                "doc_id": self.doc_id,
                "page": p.number,
                "engine": p.quality.engine,
                "attempts": p.quality.attempts,
                "confidence": round(p.quality.confidence, 3),
                "seconds": round(p.quality.seconds, 3),
                "cost_usd": round(p.quality.cost_usd, 6),
                "flags": p.quality.flags,
                "needs_review": p.quality.needs_review,
                "blocks": len(p.blocks),
                "tables": len(p.tables),
            }
            for p in self.pages
        ]
