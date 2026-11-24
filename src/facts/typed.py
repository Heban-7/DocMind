"""Typed facts read from the structured document model.

Every numeric table cell becomes a fact with its row label (and the section
row above it), column label, period, signed value, scale and unit stated by
the table ("in ETB million", "Birr '000", a "%" column), page, table id,
row and column, and the cell's box. Numbers in running text become facts
with the words before them as the label. Nothing is read from Markdown, so
a fact's page is the page the number is printed on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.document.model import Block, BlockType, DocumentModel, Page, Table
from src.facts.models import FactRecord
from src.facts.numbers import Number, find_numbers, find_period, looks_like_year, parse_cell, scale_and_currency, states_percent

_ALPHA = re.compile(r"[A-Za-z\u1200-\u137F]")
_WS = re.compile(r"\s+")
_LABEL_TAIL = re.compile(
    r"\b(?:was|were|is|are|of|at|to|by|from|with|reached|totalled|totaled|amounted|stood|grew|rose|fell|"
    r"increased|decreased|declined|about|approximately|nearly|over|under|around|an?|the|and|in|for|on)\s*$",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return _WS.sub(" ", (text or "").replace("|", " ")).strip(" :;,.-–")


def normalize_period(text: str) -> str:
    """A canonical key for matching periods: ``FY 2020/21`` and ``2020-2021`` -> ``2020/21``.

    Months keep their name (``march 2017``); a lone year stays ``2017``.
    """
    t = (text or "").lower()
    m = re.search(r"((?:19|20)\d{2})\s*[/\-–]\s*(\d{2,4})", t)
    if m:
        second = m.group(2)[-2:]
        return f"{m.group(1)}/{second}"
    month = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\D{0,6}((?:19|20)\d{2})", t
    )
    if month:
        return f"{month.group(1)} {month.group(2)}"
    q = re.search(r"\b(q[1-4]|h[12])\D{0,4}((?:19|20)\d{2})", t)
    if q:
        return f"{q.group(1)} {q.group(2)}"
    y = re.search(r"(?:19|20)\d{2}", t)
    return y.group(0) if y else ""


# --- Tables --------------------------------------------------------------------


def _is_numeric(text: str) -> bool:
    n = parse_cell(text)
    return n is not None and not looks_like_year(n)


def _is_header_row(row: list[str]) -> bool:
    filled = [c for c in row if c.strip()]
    if not filled:
        return False
    return not any(_is_numeric(c) for c in filled)


def _header_rows(table: Table, grid: list[list[str]]) -> int:
    marked = table.header_rows()
    if marked:
        return marked
    n = 0
    while n < min(3, len(grid) - 1) and _is_header_row(grid[n]):
        n += 1
    return n


def _label_column(grid: list[list[str]], start: int, n_cols: int) -> int:
    best, best_score = 0, -1
    for c in range(min(n_cols, 3)):
        score = sum(1 for r in grid[start:] if c < len(r) and _ALPHA.search(r[c]) and not _is_numeric(r[c]))
        if score > best_score:
            best, best_score = c, score
    return best


def _column_labels(table: Table, n_header: int) -> list[str]:
    parts: list[list[str]] = [[] for _ in range(table.n_cols)]
    for cell in sorted(table.cells, key=lambda c: (c.row, c.col)):
        if cell.row >= n_header or not cell.text.strip():
            continue
        for col in range(cell.col, min(table.n_cols, cell.col + max(1, cell.col_span))):
            if not parts[col] or parts[col][-1] != cell.text.strip():
                parts[col].append(cell.text.strip())
    return [_clean(" / ".join(p)) for p in parts]


def _text_above(page: Page, table: Table, max_blocks: int = 3) -> str:
    """The blocks just before the table in reading order (where "in ETB million" usually is)."""
    for i, b in enumerate(page.blocks):
        if b.type is BlockType.TABLE and b.text == table.table_id:
            before = [x.text for x in page.blocks[max(0, i - max_blocks) : i] if x.type is not BlockType.TABLE]
            return " ".join(before)
    return ""


@dataclass
class _TableContext:
    column_labels: list[str]
    scale: float
    currency: str
    title: str
    percent: bool = False


_EMBEDDED_TITLE = re.compile(r"\bTable\s+\d+(?:\.\d+)*\s*[:.].{3,160}", re.IGNORECASE)


def _cell_box(table: Table, row: int, col: int) -> list[float] | None:
    for c in table.cells:
        if c.row == row and c.col == col and c.bbox is not None:
            return [round(v, 2) for v in c.bbox.as_list()]
    return None


def facts_from_table(
    page: Page,
    table: Table,
    *,
    doc_id: str,
    document_name: str,
    previous: _TableContext | None = None,
) -> tuple[list[FactRecord], _TableContext]:
    grid = table.grid()
    if not grid:
        return [], previous or _TableContext([], 1.0, "", "")
    n_header = _header_rows(table, grid)
    labels = _column_labels(table, n_header)
    if not any(labels) and previous is not None and len(previous.column_labels) == table.n_cols:
        labels = previous.column_labels  # a continued table without its header row
    header_text = " ".join(" ".join(r) for r in grid[:n_header])
    # Docling sometimes drops the caption into a cell ("... Table 1: ... Rate (%, Year-on-Year)").
    embedded = next(
        (m.group(0) for r in grid for cell in r for m in [_EMBEDDED_TITLE.search(cell)] if m), ""
    )
    caption = table.caption or embedded
    context = " ".join([caption, header_text, _text_above(page, table)])
    scale, currency = scale_and_currency(context)
    table_percent = scale == 1.0 and not currency and states_percent(context)
    if scale == 1.0 and not currency and previous is not None and table.continued_from:
        scale, currency = previous.scale, previous.currency
        table_percent = table_percent or previous.percent
    title = _clean(caption) or (previous.title if previous is not None and table.continued_from else "")
    label_col = _label_column(grid, n_header, table.n_cols)

    facts: list[FactRecord] = []
    group = ""
    last_label = ""
    pending = ""  # a label-only row right above: OCR'd statements often put the values on the next row
    for r in range(n_header, len(grid)):
        row = grid[r]
        label = _clean(row[label_col]) if label_col < len(row) else ""
        cells: list[tuple[int, Number, float]] = []  # column, number, confidence factor
        for c, text in enumerate(row):
            if c == label_col:
                # "Provision for Unearned Premium 260,239,974": a label cell that swallowed a value
                inline = [x for x in find_numbers(text) if not looks_like_year(x)]
                if inline and _ALPHA.search(text[: inline[0].start]):
                    label = _clean(text[: inline[0].start])
                    cells.extend((c, x, 0.7) for x in inline)
                continue
            n = parse_cell(text)
            if n is not None:
                cells.append((c, n, 1.0))
            elif any(ch.isdigit() for ch in text):
                # "130,267,146 2,823,930": two columns merged into one cell
                found = [x for x in find_numbers(text) if not looks_like_year(x)]
                cells.extend((c, x, 0.7) for x in found)
        if not cells:
            if label:
                if pending:
                    group = pending  # two label rows in a row: the first is a section heading
                pending = label
            continue
        if not label and pending:
            label, pending = pending, ""
        elif not label:
            label = last_label
        elif pending:
            group, pending = pending, ""  # a section row: "Assets", "Operating income"
        last_label = label
        for c, n, factor in cells:
            col_label = labels[c] if c < len(labels) else ""
            col_scale, col_currency = scale_and_currency(col_label)
            percent = n.percent or "%" in col_label or "percent" in col_label.lower() or (table_percent and not n.currency)
            unit = "%" if percent else (n.currency or col_currency or currency)
            fact_scale = 1.0 if percent else (col_scale if col_scale != 1.0 else scale)
            period = find_period(col_label) or find_period(label) or find_period(title)
            facts.append(
                FactRecord(
                    doc_id=doc_id,
                    document_name=document_name,
                    metric=label or group or col_label or "value",
                    row_label=label,
                    row_group=group,
                    column_label=col_label,
                    table_title=title,
                    value=n.value,
                    value_text=n.text,
                    scale=fact_scale,
                    unit=unit,
                    currency=n.currency or col_currency or currency,
                    period=period,
                    page_number=page.number,
                    table_id=table.table_id,
                    row_index=r,
                    col_index=c,
                    bbox=_cell_box(table, r, c),
                    source="table",
                    confidence=round(page.quality.confidence * factor, 3),
                    source_excerpt=_clean(f"{label} | {col_label} | {n.text}")[:240],
                    extractor="typed-table",
                )
            )
    return facts, _TableContext(labels, scale, currency, title, table_percent)


# --- Markdown tables inside text (vision transcriptions) -------------------------


def _markdown_grid(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith("|") and s.count("|") >= 2):
            continue
        if re.fullmatch(r"\|[\s:\-|]+\|?", s):
            continue
        rows.append([c.strip() for c in s.strip("|").split("|")])
    return rows


def _facts_from_markdown(page: Page, block: Block, *, doc_id: str, document_name: str, index: int) -> list[FactRecord]:
    from src.document.model import TableCell

    grid = _markdown_grid(block.text)
    if len(grid) < 2:
        return []
    n_cols = max(len(r) for r in grid)
    cells = [
        TableCell(row=r, col=c, text=t, is_header=(r == 0))
        for r, row in enumerate(grid)
        for c, t in enumerate(row)
    ]
    table = Table(table_id=f"p{page.number}-md{index}", n_rows=len(grid), n_cols=n_cols, cells=cells)
    facts, _ = facts_from_table(page, table, doc_id=doc_id, document_name=document_name)
    return facts


# --- Running text ----------------------------------------------------------------

_SENTENCE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(\u1200-\u137F])")


def _prose_label(sentence: str, start: int) -> str:
    before = sentence[:start]
    before = re.split(r"[;:,(]\s*(?=[^;:,(]*$)", before)[-1] if before.count(",") > 2 else before
    words = _clean(before).split()[-12:]
    label = " ".join(words)
    for _ in range(3):
        label = _LABEL_TAIL.sub("", label).strip(" :;,.-–")
    return label


_UNIT_AFTER = re.compile(r"\s*[a-z]{3,}", re.IGNORECASE)


def facts_from_text(
    page: Page, block: Block, *, doc_id: str, document_name: str, previous_text: str = ""
) -> list[FactRecord]:
    facts: list[FactRecord] = []
    text = _WS.sub(" ", block.text)
    bbox = [round(v, 2) for v in block.bbox.as_list()] if block.bbox is not None else None
    for i, sentence in enumerate(_SENTENCE.split(text)):
        for n in find_numbers(sentence):
            digits = re.sub(r"\D", "", n.text)
            small = len(digits) < 2 and not n.percent and n.scale == 1.0 and not n.currency
            # "within 5 business days" is a fact; "1." in a list is not
            if looks_like_year(n) or (small and not (_UNIT_AFTER.match(sentence[n.end:]) and n.start > 0)):
                continue
            label = _prose_label(sentence, n.start)
            if not _ALPHA.search(label) and i == 0 and previous_text:
                # a sentence broken by a heading: "... the rate" / "## Summary" / "was 26.2 percent"
                label = _prose_label(previous_text + " " + sentence[: n.start], len(previous_text) + 1 + n.start)
            if not _ALPHA.search(label):
                continue
            facts.append(
                FactRecord(
                    doc_id=doc_id,
                    document_name=document_name,
                    metric=label,
                    row_label=label,
                    value=n.value,
                    value_text=n.text.lstrip("(") if n.text.startswith("(") and not n.text.endswith(")") else n.text,
                    scale=n.scale,
                    unit="%" if n.percent else n.currency,
                    currency=n.currency,
                    period=find_period(sentence),
                    page_number=page.number,
                    bbox=bbox,
                    source="text",
                    confidence=page.quality.confidence,
                    source_excerpt=sentence[:240],
                    extractor="typed-text",
                )
            )
    return facts


def facts_from_model(model: DocumentModel, *, doc_id: str, document_name: str = "") -> list[FactRecord]:
    """Every fact of a document, page by page, tables first."""
    out: list[FactRecord] = []
    contexts: dict[str, _TableContext] = {}
    for page in model.pages:
        for table in page.tables:
            prev = contexts.get(table.continued_from) if table.continued_from else None
            facts, ctx = facts_from_table(page, table, doc_id=doc_id, document_name=document_name, previous=prev)
            contexts[table.table_id] = ctx
            out.extend(facts)
        md_index = 0
        previous_text = ""
        for block in page.blocks:
            if block.type in (BlockType.TABLE, BlockType.PAGE_HEADER, BlockType.PAGE_FOOTER, BlockType.FIGURE):
                continue
            if block.text.count("|") >= 4 and _markdown_grid(block.text):
                out.extend(_facts_from_markdown(page, block, doc_id=doc_id, document_name=document_name, index=md_index))
                md_index += 1
                continue
            if block.type in (BlockType.TEXT, BlockType.LIST_ITEM, BlockType.CAPTION, BlockType.FOOTNOTE, BlockType.HEADING, BlockType.TITLE):
                out.extend(
                    facts_from_text(page, block, doc_id=doc_id, document_name=document_name, previous_text=previous_text)
                )
                if block.type not in (BlockType.HEADING, BlockType.TITLE) and _ALPHA.search(block.text):
                    previous_text = block.text[-200:]
    return [f.model_copy(update={"period_key": normalize_period(f.period or f.column_label)}) for f in out]
