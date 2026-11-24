"""Render a DocumentModel as Markdown for the existing chunker.

Page markers (``<!-- page N -->``) keep page attribution; tables are GitHub
tables with their header row, and a table continued from the previous page
repeats that page's header so no table chunk loses its columns. Pages with
no content say so (``<!-- page N failed: reason -->``) instead of vanishing.
"""

from __future__ import annotations

from src.document.model import BlockType, DocumentModel, Page, Table


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def _table_md(table: Table, header_from: Table | None = None) -> str:
    grid = table.grid()
    n_head = table.header_rows()
    if n_head:
        header = [" ".join(_cell(grid[r][c]) for r in range(n_head)).strip() for c in range(table.n_cols)]
        body = grid[n_head:]
    elif header_from is not None:
        hg = header_from.grid()
        hn = max(1, header_from.header_rows())
        header = [" ".join(_cell(hg[r][c]) for r in range(hn)).strip() for c in range(table.n_cols)]
        body = grid
    else:
        header = [_cell(v) for v in grid[0]] if grid else []
        body = grid[1:]
    if not header:
        return ""
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for row in body:
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return "\n".join(lines)


def render_page(page: Page, tables_by_id: dict[str, Table]) -> str:
    parts = [f"<!-- page {page.number} -->"]
    has_text = any(
        b.text.strip()
        for b in page.blocks
        if b.type not in (BlockType.FIGURE, BlockType.TABLE, BlockType.PAGE_HEADER, BlockType.PAGE_FOOTER)
    )
    no_text_flag = any(
        f.startswith(("no readable text", "no text could", "little or no readable text")) for f in page.quality.flags
    )
    if (not has_text and not page.tables) or no_text_flag:
        reason = "; ".join(page.quality.flags) or "no content"
        parts.append(f"<!-- page {page.number} failed: {reason} -->")
        if not has_text and not page.tables:
            return "\n\n".join(parts)
    # A table's caption is printed right above the table (so the chunker keeps
    # them together), and skipped where Docling placed it in reading order.
    table_captions = {" ".join(t.caption.split()) for t in page.tables if t.caption}
    placed: set[str] = set()
    for b in page.blocks:
        if b.type in (BlockType.PAGE_HEADER, BlockType.PAGE_FOOTER):
            continue
        if b.type is BlockType.CAPTION and " ".join(b.text.split()) in table_captions:
            continue
        if b.type is BlockType.TABLE:
            t = tables_by_id.get(b.text)
            if t is None:
                continue
            placed.add(t.table_id)
            if t.caption:
                parts.append(" ".join(t.caption.split()))
            md = _table_md(t, tables_by_id.get(t.continued_from) if t.continued_from else None)
            if md:
                parts.append(md)
            continue
        text = b.text.strip()
        if not text and b.type is not BlockType.FIGURE:
            continue
        if b.type in (BlockType.HEADING, BlockType.TITLE):
            level = 1 if b.type is BlockType.TITLE else min(6, max(1, (b.level or 2)))
            parts.append("#" * level + " " + " ".join(text.split()))
        elif b.type is BlockType.LIST_ITEM:
            parts.append(text if text[:1] in "-*•" else f"- {text}")
        elif b.type is BlockType.FIGURE:
            parts.append("<!-- figure -->" if not text else f"<!-- figure -->\n{text}")
        else:
            parts.append(text)
    for t in page.tables:  # tables without a reading-order marker (OCR pages, vision)
        if t.table_id not in placed:
            md = _table_md(t, tables_by_id.get(t.continued_from) if t.continued_from else None)
            if md:
                parts.append(md)
    return "\n\n".join(parts)


def render_markdown(model: DocumentModel) -> str:
    tables_by_id = {t.table_id: t for p in model.pages for t in p.tables}
    return "\n\n".join(render_page(p, tables_by_id) for p in model.pages).strip() + "\n"
