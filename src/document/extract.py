"""Page-level routing, quality checks and escalation.

Every page is triaged on its own:

* text layer present and clean, no table -> read from the text layer (milliseconds)
* text layer present with a table        -> Docling layout + TableFormer, with every
                                             cell and block re-read from the text layer
* no usable text layer (scan, broken)    -> Docling with Tesseract OCR (amh+eng)
* OCR found nothing or scored low        -> vision model, if configured and the page
                                             is not Ethiopic script; flagged for review

Nothing is dropped silently: every page ends with content or with a flag that
says why it has none, and the per-page ledger records engine, confidence, time
and cost.
"""

from __future__ import annotations

import hashlib
import logging
import re
import statistics
import time
from collections import Counter
from pathlib import Path

import pdfplumber

from src.document import docling_engine
from src.document.model import BBox, Block, BlockType, DocumentModel, Page, PageQuality, Table
from src.document.text_layer import (
    TextLayerPage,
    analyse_page,
    blocks_from_lines,
    garbled_ratio,
    looks_like_table_page,
    script_of,
    text_in_box,
)

logger = logging.getLogger("docmind.document")

MIN_TEXT_CHARS = 30
MAX_GARBLED = 0.05
OCR_LOW_CONFIDENCE = 0.5
HEADER_ZONE = 0.07  # top/bottom share of the page where running headers live


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _image_coverage(page) -> float:
    area = float(page.width * page.height) or 1.0
    covered = 0.0
    for im in page.images:
        x0, x1 = max(0.0, float(im["x0"])), min(float(page.width), float(im["x1"]))
        t, b = max(0.0, float(im["top"])), min(float(page.height), float(im["bottom"]))
        if x1 > x0 and b > t:
            covered += (x1 - x0) * (b - t)
    return min(1.0, covered / area)


def _route(tl: TextLayerPage, image_cov: float) -> str:
    if tl.char_count < MIN_TEXT_CHARS or garbled_ratio(tl) > MAX_GARBLED:
        return "ocr"
    if tl.char_count < 200 and image_cov > 0.5:
        return "ocr"  # a scan with a few stray characters on top
    if looks_like_table_page(tl):
        return "docling"
    return "text"


def _heading_levels(text_pages: list[TextLayerPage]) -> dict[float, int]:
    """Map heading font sizes to levels 1-3 for the whole document."""
    bodies = [tl.body_size for tl in text_pages if tl.body_size]
    if not bodies:
        return {}
    body = statistics.median(bodies)
    sizes: Counter = Counter()
    for tl in text_pages:
        for ln in tl.lines:
            if ln.size >= body * 1.15 and len(ln.words) <= 14:
                sizes[ln.size] += 1
    ranked = sorted((s for s, n in sizes.items() if n >= 1), reverse=True)[:3]
    return {s: i + 1 for i, s in enumerate(ranked)}


def _reread(block: Block, tl: TextLayerPage | None) -> Block:
    if tl is None or block.bbox is None or block.type is BlockType.TABLE:
        return block
    text = text_in_box(tl.words, block.bbox)
    if text:
        return block.model_copy(update={"text": text})
    return block


def _reread_table(table: Table, tl: TextLayerPage | None) -> tuple[Table, float]:
    """Replace cell text with the PDF's own words; return the share replaced."""
    if tl is None:
        return table, 0.0
    replaced = 0
    cells = []
    for c in table.cells:
        if c.bbox is not None:
            text = text_in_box(tl.words, c.bbox, slack=1.0)
            if text:
                cells.append(c.model_copy(update={"text": text, "text_source": "text_layer"}))
                replaced += 1
                continue
        cells.append(c)
    return table.model_copy(update={"cells": cells}), replaced / max(1, len(table.cells))


def _table_checks(table: Table) -> dict:
    grid = table.grid()
    filled = sum(1 for row in grid for v in row if v.strip())
    numeric = sum(1 for row in grid for v in row if re.fullmatch(r"\(?-?[\d,]+(?:\.\d+)?\)?%?", v.strip() or "x"))
    width_ok = sum(1 for row in grid if sum(1 for v in row if v.strip()) >= 2)
    return {
        "fill_ratio": round(filled / max(1, table.n_rows * table.n_cols), 3),
        "numeric_cells": numeric,
        "rows_with_2plus_cells": width_ok,
        "has_header": table.header_rows() > 0,
    }


def _heading_level_for(block: Block, tl: TextLayerPage | None, levels: dict[float, int]) -> int:
    if tl is not None and block.bbox is not None and levels:
        sizes = [w.size for w in tl.words if block.bbox.contains_point(w.cx, w.cy, 1.5) and w.size]
        if sizes:
            s = statistics.median(sizes)
            if s in levels:
                return levels[s]
            bigger = [lvl for size, lvl in levels.items() if size <= s]
            if bigger:
                return min(bigger)
    return max(levels.values()) + 1 if levels else 2


def _mark_running_headers(pages: list[Page]) -> None:
    """Lines repeated near the top or bottom of many pages are headers/footers."""
    def key(text: str) -> str:
        return re.sub(r"\d+", "#", text.lower()).strip()

    counts: Counter = Counter()
    for p in pages:
        seen = set()
        for b in p.blocks:
            if b.bbox and b.type in (BlockType.TEXT, BlockType.HEADING) and (
                b.bbox.bottom < p.height * HEADER_ZONE or b.bbox.top > p.height * (1 - HEADER_ZONE)
            ):
                seen.add(key(b.text))
        counts.update(seen)
    threshold = max(3, int(len(pages) * 0.25))
    repeated = {k for k, n in counts.items() if n >= threshold}
    if not repeated:
        return
    for p in pages:
        new_blocks = []
        for b in p.blocks:
            if b.bbox and key(b.text) in repeated:
                top = b.bbox.bottom < p.height * HEADER_ZONE
                b = b.model_copy(update={"type": BlockType.PAGE_HEADER if top else BlockType.PAGE_FOOTER})
            new_blocks.append(b)
        p.blocks = new_blocks


def _link_continued_tables(pages: list[Page]) -> None:
    """A header-less table at the top of a page continues the last table of the previous page."""
    for prev, cur in zip(pages, pages[1:]):
        if not prev.tables or not cur.tables:
            continue
        last, first = prev.tables[-1], cur.tables[0]
        near_top = first.bbox is None or first.bbox.top < cur.height * 0.35
        if near_top and first.header_rows() == 0 and first.n_cols == last.n_cols and last.n_cols >= 2:
            cur.tables[0] = first.model_copy(update={"continued_from": last.continued_from or last.table_id})


def _vision_page(pdf_path: Path, page_no: int, client, guard) -> tuple[list[Block], float, str | None]:
    """Transcribe one page with a vision model. No boxes; always flagged."""
    from src.extraction.page_render import render_pages_to_png
    from src.llm.budget import BudgetExceededError

    try:
        guard.assert_can_spend()
    except BudgetExceededError as exc:
        return [], 0.0, f"vision budget reached: {exc}"
    import pypdfium2 as pdfium
    from io import BytesIO

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        img = doc[page_no - 1].render(scale=150 / 72).to_pil()
        buf = BytesIO()
        img.save(buf, format="PNG")
    finally:
        doc.close()
    _ = render_pages_to_png  # kept for API parity with the V1 vision engine
    prompt = (
        "Transcribe this page exactly as printed, as GitHub-Flavored Markdown. Keep tables as Markdown tables. "
        "Copy every number character for character. If a word or number is illegible, write [illegible] "
        "instead of guessing. Output only the transcription."
    )
    result = client.analyze_image(buf.getvalue(), prompt)
    guard.record(result.cost_usd)
    # Models often wrap the transcription in a ``` fence; an unclosed fence would
    # swallow the rest of the document downstream, so fences are removed.
    text = "\n".join(ln for ln in result.text.strip().splitlines() if not ln.strip().startswith("```"))
    blocks = []
    for i, para in enumerate(p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()):
        blocks.append(Block(block_id=f"p{page_no}-b{i}", type=BlockType.TEXT, text=para.strip()))
    return blocks, result.cost_usd, None


def extract_document(pdf_path: str | Path, *, vision_client=None, allow_vision: bool = True) -> DocumentModel:
    pdf_path = Path(pdf_path)
    started = time.perf_counter()
    sha = sha256_of(pdf_path)
    doc_id = sha[:12]

    routes: dict[int, str] = {}
    layers: dict[int, TextLayerPage] = {}
    sizes: dict[int, tuple[float, float]] = {}
    images: dict[int, float] = {}
    triage_seconds: dict[int, float] = {}
    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            t0 = time.perf_counter()
            try:
                tl = analyse_page(page)
                cov = _image_coverage(page)
            except Exception as exc:  # unreadable text layer: treat as a scan
                logger.warning("text layer unreadable on page %s: %s", i, exc)
                tl, cov = None, 1.0
            sizes[i] = (float(page.width), float(page.height))
            images[i] = cov
            if tl is not None:
                layers[i] = tl
            routes[i] = "ocr" if tl is None else _route(tl, cov)
            triage_seconds[i] = time.perf_counter() - t0
            page.flush_cache()

    levels = _heading_levels([layers[p] for p, r in routes.items() if r != "ocr" and p in layers])
    table_pages = [p for p, r in routes.items() if r == "docling"]
    ocr_pages = [p for p, r in routes.items() if r == "ocr"]
    docling_out = docling_engine.convert_pages(pdf_path, table_pages, ocr=False)
    ocr_out = docling_engine.convert_pages(pdf_path, ocr_pages, ocr=True)

    guard = None
    if allow_vision and vision_client is None:
        try:
            from src.llm.factory import build_vision_client

            vision_client = build_vision_client()
        except Exception:
            vision_client = None
    if vision_client is not None:
        from src.config import VisionConfig
        from src.llm.budget import BudgetGuard

        guard = BudgetGuard(VisionConfig.BUDGET_USD)

    pages: list[Page] = []
    for n in range(1, n_pages + 1):
        width, height = sizes[n]
        tl = layers.get(n)
        route = routes[n]
        flags: list[str] = []
        attempts: list[str] = []
        checks: dict = {"image_coverage": round(images[n], 3)}
        if tl is not None:
            checks.update(tl.checks)
            checks["garbled_ratio"] = round(garbled_ratio(tl), 4)
        seconds = triage_seconds[n]
        cost = 0.0
        blocks: list[Block] = []
        tables: list[Table] = []
        engine = route
        confidence = 0.0
        script = script_of(tl) if tl is not None else "none"

        if route == "docling":
            attempts.append("docling")
            dp = docling_out.get(n)
            seconds += (dp.scores.get("seconds", 0.0) if dp else 0.0)
            if dp is None or dp.error:
                flags.append(f"docling failed ({dp.error if dp else 'no result'}); text layer used")
                route = "text"
            else:
                blocks = [_reread(b, tl) for b in dp.blocks]
                for b in blocks:
                    if b.type is BlockType.HEADING:
                        b.level = _heading_level_for(b, tl, levels)
                reread_share = []
                for t in dp.tables:
                    t2, share = _reread_table(t, tl)
                    tables.append(t2)
                    reread_share.append(share)
                    checks[f"{t2.table_id}"] = str(_table_checks(t2))
                checks["cells_from_text_layer"] = round(statistics.mean(reread_share), 3) if reread_share else 0.0
                confidence = min(dp.scores.get("layout_score", 0.9), dp.scores.get("table_score", 0.9), 0.98)
                engine = "docling"
                if not tables:
                    checks["docling_found_no_table"] = True

        if route == "text":
            attempts.append("text_layer")
            t0 = time.perf_counter()
            blocks = blocks_from_lines(tl.lines, n, tl.body_size, levels) if tl else []
            seconds += time.perf_counter() - t0
            engine = "text_layer"
            confidence = max(0.0, 0.98 - garbled_ratio(tl) * 5) if tl else 0.0

        if route == "ocr":
            attempts.append(f"ocr:{docling_engine.ocr_engine_name()}")
            dp = ocr_out.get(n)
            seconds += (dp.scores.get("seconds", 0.0) if dp else 0.0)
            engine = "ocr"
            if dp is None or dp.error:
                flags.append(f"OCR failed ({dp.error if dp else 'no result'})")
            else:
                blocks, tables = dp.blocks, dp.tables
                confidence = dp.scores.get("ocr_score", 0.6)
                text = " ".join(b.text for b in blocks) + " ".join(c.text for t in tables for c in t.cells)
                eth = len(re.findall(r"[ሀ-፿]", text))
                lat = len(re.findall(r"[A-Za-z]", text))
                script = "ethiopic" if eth > lat else ("mixed" if eth > 0.1 * max(1, lat) else ("latin" if lat else "none"))
                if docling_engine.ocr_engine_name() != "tesseract":
                    flags.append("Tesseract not installed: Amharic cannot be read")
                if script in ("ethiopic", "mixed"):
                    flags.append("Amharic OCR: check against the page")
            has_text = any(b.text.strip() for b in blocks) or bool(tables)
            low = confidence < OCR_LOW_CONFIDENCE or not has_text
            if low and script not in ("ethiopic", "mixed") and vision_client is not None and guard is not None:
                attempts.append("vision")
                t0 = time.perf_counter()
                try:
                    vblocks, vcost, err = _vision_page(pdf_path, n, vision_client, guard)
                except Exception as exc:
                    vblocks, vcost, err = [], 0.0, f"vision failed: {type(exc).__name__}: {exc}"
                seconds += time.perf_counter() - t0
                cost += vcost
                if vblocks:
                    blocks, tables = vblocks, []
                    engine = "vision"
                    confidence = 0.5
                    flags.append("vision transcription: no boxes, verify numbers against the page")
                elif err:
                    flags.append(err)
            if not any(b.text.strip() for b in blocks) and not tables:
                flags.append("no text could be extracted from this page")

        body = "".join(
            b.text for b in blocks if b.type not in (BlockType.FIGURE, BlockType.TABLE, BlockType.PAGE_HEADER, BlockType.PAGE_FOOTER)
        )
        if not tables and len(re.sub(r"\s+", "", body)) < MIN_TEXT_CHARS and not any("no text" in f for f in flags):
            flags.append("no readable text on this page (image-only or blank)")
        needs_review = bool(flags) or confidence < OCR_LOW_CONFIDENCE
        pages.append(
            Page(
                number=n,
                width=width,
                height=height,
                blocks=blocks,
                tables=tables,
                script=script,
                quality=PageQuality(
                    engine=engine,
                    confidence=round(max(0.0, min(1.0, confidence)), 3),
                    checks=checks,
                    flags=flags,
                    attempts=attempts,
                    seconds=round(seconds, 3),
                    cost_usd=round(cost, 6),
                    needs_review=needs_review,
                ),
            )
        )

    _mark_running_headers(pages)
    _link_continued_tables(pages)
    return DocumentModel(
        doc_id=doc_id,
        file_name=pdf_path.name,
        sha256=sha,
        page_count=n_pages,
        pages=pages,
        seconds=round(time.perf_counter() - started, 3),
        cost_usd=round(sum(p.quality.cost_usd for p in pages), 6),
    )


def bbox_union(boxes: list[BBox]) -> BBox | None:
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    out = boxes[0]
    for b in boxes[1:]:
        out = out.union(b)
    return out
