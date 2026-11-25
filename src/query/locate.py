"""Find where on its page a cited claim is printed.

A citation from a chunk used to carry a box around the whole page. With the
document model saved next to the PDF (``model.json``), the box can be the
table cell that prints the number the answer states (plus the row's label,
so a reader sees which row it is), or the text blocks the passage came from.

Coordinates in the model are PDF points from the TOP-LEFT corner; citation
boxes are from the BOTTOM-LEFT corner (PDF convention), so they are flipped
here with the page height.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

from src.document.model import BBox, BlockType, DocumentModel, Page
from src.facts.numbers import Number, find_numbers, looks_like_year
from src.models.provenance import BoundingBox

logger = logging.getLogger("docmind.provenance")

_WORD = re.compile(r"[^\W_]{2,}", re.UNICODE)
_SKIP_BLOCKS = (BlockType.PAGE_HEADER, BlockType.PAGE_FOOTER, BlockType.TABLE)


@lru_cache(maxsize=8)
def _load(path: str, mtime: float) -> DocumentModel | None:
    try:
        return DocumentModel.model_validate_json(Path(path).read_bytes())
    except Exception as exc:  # a broken model only costs the precise box
        logger.warning("could not read document model %s: %s", path, exc)
        return None


def model_beside(pdf_path: str | Path | None) -> DocumentModel | None:
    """The document model stored beside a document's PDF, when there is one."""
    if not pdf_path:
        return None
    path = Path(pdf_path).with_name("model.json")
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return _load(str(path), mtime)


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")}


def _holds(text: str, n: Number) -> bool:
    """Does ``text`` print the number ``n`` (scale words and units aside)?"""
    from src.query.verify import EvidenceNumbers

    return EvidenceNumbers(text).holds(n)


def _cell_number(text: str) -> bool:
    nums = [n for n in find_numbers(text or "") if not looks_like_year(n)]
    return bool(nums) and len(_words(re.sub(r"\d", " ", text or ""))) <= 2


def _to_box(b: BBox, page: Page) -> BoundingBox:
    return BoundingBox(
        x0=round(b.x0, 2), y0=round(page.height - b.bottom, 2), x1=round(b.x1, 2), y1=round(page.height - b.top, 2),
        page_width=page.width, page_height=page.height,
    )


def _number_boxes(page: Page, numbers: list[Number], context: str) -> tuple[list[BBox], bool]:
    """The cells (and their row labels) or blocks that print ``numbers``; True when a cell."""
    ctx = _words(context)
    found: list[BBox] = []
    in_table = False
    for n in numbers:
        candidates: list[tuple[float, list[BBox], bool]] = []
        for table in page.tables:
            rows: dict[int, list] = {}
            for c in table.cells:
                rows.setdefault(c.row, []).append(c)
            for c in table.cells:
                if c.bbox is None or not c.text or not _cell_number(c.text) or not _holds(c.text, n):
                    continue
                row = sorted(rows.get(c.row, []), key=lambda x: x.col)
                label = next((x for x in row if x.bbox is not None and x.text and not _cell_number(x.text)), None)
                header = " ".join(x.text for x in table.cells if x.col == c.col and x.row < c.row and x.is_header)
                row_words = _words(" ".join(x.text for x in row)) | _words(header)
                score = len(row_words & ctx) + (0.5 if not c.is_header else 0.0)
                # the same figure under a business line and under Total: the Total is the answer
                score += 0.25 if "total" in _words(header) else 0.0
                boxes = [c.bbox] + ([label.bbox] if label is not None and label is not c else [])
                candidates.append((score, boxes, True))
        for block in page.blocks:
            if block.bbox is None or block.type in _SKIP_BLOCKS or not _holds(block.text, n):
                continue
            # a number in running text: the block is the smallest box the model knows
            score = len(_words(block.text) & ctx) * 0.25 - 0.5
            candidates.append((score, [block.bbox], False))
        if candidates:
            best = max(candidates, key=lambda c: c[0])
            # two places print it equally well: a box on either would be a guess
            if sum(1 for c in candidates if c[0] == best[0]) > 1 and len(candidates) > 1 and best[0] <= 0:
                continue
            in_table = in_table or best[2]
            for b in best[1]:
                if b not in found:
                    found.append(b)
    return found, in_table


def _passage_boxes(page: Page, excerpt: str) -> list[BBox]:
    """The blocks (and tables) whose text the passage contains."""
    ex = _words(excerpt)
    if len(ex) < 3:
        return []
    out: list[BBox] = []
    for block in page.blocks:
        if block.bbox is None or block.type in _SKIP_BLOCKS:
            continue
        words = _words(block.text)
        if len(words) >= 2 and len(words & ex) >= 0.7 * len(words):
            out.append(block.bbox)
    for table in page.tables:
        if table.bbox is None:
            continue
        words = _words(" ".join(c.text for c in table.cells))
        if len(words) >= 3 and len(words & ex) >= 0.6 * len(words):
            out.append(table.bbox)
    # a passage that matches most of the page is the page
    area = sum(b.width * b.height for b in out)
    if out and area > 0.6 * page.width * page.height:
        return []
    return out


def locate_on_pages(
    model: DocumentModel | None,
    pages: list[int],
    *,
    numbers: list[str] | None = None,
    context: str = "",
    excerpt: str = "",
) -> tuple[int, list[BoundingBox], str]:
    """Like ``locate`` for a passage that runs over several pages.

    The first page that prints the answer's figures wins (a chunk that starts
    on page 19 may print the figure on page 20); otherwise the first page
    with the passage's blocks; otherwise the first page itself.
    """
    pages = list(dict.fromkeys(p for p in pages if p))
    if not pages:
        return 1, [], "page"
    if numbers and model is not None:
        for page in pages:
            boxes, kind = locate(model, page, numbers=numbers, context=context, excerpt="", figures_only=True)
            if boxes:
                return page, boxes, kind
    boxes, kind = locate(model, pages[0], numbers=None, context=context, excerpt=excerpt)
    return pages[0], boxes, kind


def locate(
    model: DocumentModel | None,
    page_number: int,
    *,
    numbers: list[str] | None = None,
    context: str = "",
    excerpt: str = "",
    figures_only: bool = False,
) -> tuple[list[BoundingBox], str]:
    """Boxes on ``page_number`` for a claim, and what they mark.

    ``numbers`` are the figures the answer states and this evidence holds (as
    printed in the answer); ``context`` is the answer's sentences that cite
    it. Returns ``([], "page")`` when nothing smaller than the page is known.
    """
    if model is None or not (1 <= page_number <= len(model.pages)):
        return [], "page"
    page = model.page(page_number)
    if not page.width or not page.height:
        return [], "page"
    parsed: list[Number] = []
    for text in numbers or []:
        parsed.extend(n for n in find_numbers(text) if not looks_like_year(n))
    if parsed:
        boxes, in_table = _number_boxes(page, parsed, context + " " + excerpt)
        if boxes:
            return [_to_box(b, page) for b in boxes], "cell" if in_table else "block"
    if figures_only:
        return [], "page"
    boxes = _passage_boxes(page, excerpt)
    if boxes:
        return [_to_box(b, page) for b in boxes], "block"
    return [], "page"


def union(boxes: list[BoundingBox]) -> BoundingBox:
    return BoundingBox(
        x0=min(b.x0 for b in boxes), y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes), y1=max(b.y1 for b in boxes),
        page_width=boxes[0].page_width, page_height=boxes[0].page_height,
    )
