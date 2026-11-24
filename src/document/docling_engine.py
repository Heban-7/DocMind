"""Docling for the pages that need layout analysis: tables and scans.

Only the selected pages are sent (as small sub-PDFs). Work is split into
batches that several lanes take from one queue; each lane keeps its own
converters (built once per process, reused for every document) and runs
single-threaded, which on a small CPU box is faster than one lane with
several threads. Every Docling item keeps its box. On digital pages the
caller replaces Docling's text with the PDF's own words inside each box, so
numbers are never broken by Docling's parser.
"""

from __future__ import annotations

import gc
import logging
import os
import queue
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.config import OCR_LANGUAGES
from src.document import device as _dev
from src.document.model import BBox, Block, BlockType, Table, TableCell

logger = logging.getLogger("docmind.document.docling")

_CONVERTERS: dict[tuple[bool, str, int], object] = {}
_CONVERTERS_LOCK = threading.Lock()

_LABELS = {
    "title": BlockType.TITLE,
    "section_header": BlockType.HEADING,
    "text": BlockType.TEXT,
    "paragraph": BlockType.TEXT,
    "list_item": BlockType.LIST_ITEM,
    "caption": BlockType.CAPTION,
    "footnote": BlockType.FOOTNOTE,
    "page_header": BlockType.PAGE_HEADER,
    "page_footer": BlockType.PAGE_FOOTER,
    "picture": BlockType.FIGURE,
    "chart": BlockType.FIGURE,
    "formula": BlockType.TEXT,
    "code": BlockType.TEXT,
    "reference": BlockType.TEXT,
    "key_value_region": BlockType.TEXT,
}


@dataclass
class DoclingPage:
    blocks: list[Block] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)
    error: str | None = None


def _device():
    return _dev.resolve_device()


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _ocr_options():
    from docling.datamodel.pipeline_options import TesseractCliOcrOptions

    # One Tesseract process per lane, one core each. (Letting Tesseract use
    # every core on the single-lane GPU box was slower, 431 s vs 371 s on a
    # 38-page scan, so the limit applies everywhere.)
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    return TesseractCliOcrOptions(lang=list(OCR_LANGUAGES), force_full_page_ocr=True)


def table_mode() -> str:
    """TableFormer mode. ``auto``: accurate on a GPU, fast on CPU.

    Cell text comes from the PDF's own words, so the mode only affects the
    grid. On the golden set both modes scored the same on table rows while
    fast was 1.7x quicker on 2 CPU threads (11.9 s vs 20.5 s per table page).
    """
    import os

    mode = os.getenv("DOCMIND_V2_TABLE_MODE", "auto").lower()
    if mode == "auto":
        _, is_gpu = _device()
        return "accurate" if is_gpu else "fast"
    return mode


def converter(ocr: bool, lane: int = 0):
    """One converter per (ocr, table mode, lane), built on first use and kept.

    The PDF is read with pypdfium2 rather than docling-parse: the text Docling
    reads is replaced by the text layer anyway, and on 2 CPU cores this backend
    made table pages about 20% faster with the same tables.
    """
    key = (ocr, table_mode(), lane)
    with _CONVERTERS_LOCK:
        if key in _CONVERTERS:
            return _CONVERTERS[key]
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
        from docling.document_converter import DocumentConverter, PdfFormatOption

        device, _ = _device()
        opts = PdfPipelineOptions()
        opts.accelerator_options = AcceleratorOptions(device=device, num_threads=_dev.threads_per_lane())
        opts.do_ocr = ocr
        opts.do_table_structure = True
        opts.table_structure_options.mode = (
            TableFormerMode.ACCURATE if key[1] == "accurate" else TableFormerMode.FAST
        )
        if ocr:
            opts.ocr_options = _ocr_options()
        conv = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=opts, backend=PyPdfiumDocumentBackend)
            }
        )
        _CONVERTERS[key] = conv
        return conv


def ocr_engine_name() -> str:
    return "tesseract" if tesseract_available() else "none"


def _batch_size() -> int:
    """Pages per Docling call: larger calls are faster, smaller ones report progress sooner."""
    _, is_gpu = _device()
    return max(1, int(os.getenv("DOCMIND_PAGE_BATCH", "8" if is_gpu else "4")))


def _write_subset(src: Path, pages: list[int], out: Path) -> None:
    import pypdfium2 as pdfium
    from docling.utils.locks import pypdfium2_lock  # pdfium is not thread-safe

    with pypdfium2_lock:
        doc = pdfium.PdfDocument(str(src))
        new = pdfium.PdfDocument.new()
        try:
            new.import_pages(doc, [p - 1 for p in pages])
            new.save(str(out))
        finally:
            new.close()
            doc.close()


def _to_top_left(bbox, page_height: float) -> BBox:
    from docling_core.types.doc import CoordOrigin

    if bbox.coord_origin == CoordOrigin.BOTTOMLEFT:
        return BBox.from_bottom_left(bbox.l, bbox.t, bbox.r, bbox.b, page_height)
    return BBox(x0=bbox.l, top=bbox.t, x1=bbox.r, bottom=bbox.b)


def _page_items(document, internal_page: int, original_page: int) -> DoclingPage:
    from docling_core.types.doc import ContentLayer, TableItem

    size = document.pages[internal_page].size
    out = DoclingPage(width=float(size.width), height=float(size.height))
    layers = {ContentLayer.BODY, ContentLayer.FURNITURE}
    for item, level in document.iterate_items(page_no=internal_page, included_content_layers=layers):
        # A paragraph that runs across a page break has one provenance entry per
        # page; use the one for this page, and only this page's part of the text.
        provs = list(getattr(item, "prov", None) or [])
        prov = next((p for p in provs if p.page_no == internal_page), provs[0] if provs else None)
        bbox = _to_top_left(prov.bbox, out.height) if prov else None
        if prov is not None and len(provs) > 1 and getattr(item, "text", None) and getattr(prov, "charspan", None):
            start, end = prov.charspan
            item = item.model_copy(update={"text": item.text[start:end]})
        label = str(getattr(item, "label", "")).split(".")[-1].lower()
        if isinstance(item, TableItem):
            t_index = len(out.tables)
            cells = []
            for c in item.data.table_cells:
                cells.append(
                    TableCell(
                        row=c.start_row_offset_idx,
                        col=c.start_col_offset_idx,
                        row_span=max(1, c.end_row_offset_idx - c.start_row_offset_idx),
                        col_span=max(1, c.end_col_offset_idx - c.start_col_offset_idx),
                        text=c.text.strip(),
                        bbox=_to_top_left(c.bbox, out.height) if c.bbox else None,
                        is_header=bool(c.column_header),
                    )
                )
            caption = ""
            try:
                caption = item.caption_text(document) or ""
            except Exception:
                pass
            out.tables.append(
                Table(
                    table_id=f"p{original_page}-t{t_index}",
                    bbox=bbox,
                    n_rows=item.data.num_rows,
                    n_cols=item.data.num_cols,
                    cells=cells,
                    caption=caption,
                )
            )
            # Keep the table's position in reading order.
            out.blocks.append(
                Block(block_id=f"p{original_page}-b{len(out.blocks)}", type=BlockType.TABLE, text=f"p{original_page}-t{t_index}", bbox=bbox)
            )
            continue
        text = getattr(item, "text", "") or ""
        btype = _LABELS.get(label)
        if btype is None:
            continue
        if btype is BlockType.FIGURE:
            text = text or ""
        elif not text.strip():
            continue
        out.blocks.append(
            Block(
                block_id=f"p{original_page}-b{len(out.blocks)}",
                type=btype,
                text=text.strip(),
                bbox=bbox,
                level=getattr(item, "level", None) if btype is BlockType.HEADING else None,
            )
        )
    return out


def warm_up(*, ocr: bool = True) -> float:
    """Load every lane's models now (a long-running worker calls this at start).

    Converts one blank page per lane and kind, so the first real document
    does not pay for loading the layout, table and OCR models.
    """
    import pypdfium2 as pdfium
    from docling.utils.locks import pypdfium2_lock

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        blank = Path(tmp) / "blank.pdf"
        with pypdfium2_lock:
            doc = pdfium.PdfDocument.new()
            try:
                doc.new_page(595, 842)
                doc.save(str(blank))
            finally:
                doc.close()
        kinds = [False, True] if ocr and tesseract_available() else [False]

        def load(lane: int) -> None:
            for kind in kinds:
                try:
                    converter(kind, lane).convert(blank, raises_on_error=False)
                except Exception as exc:  # warming is an optimisation only
                    logger.warning("warm-up failed (lane %s, ocr=%s): %s", lane, kind, exc)

        threads = [threading.Thread(target=load, args=(i,), daemon=True) for i in range(_dev.lanes())]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    return time.perf_counter() - started


def _convert_batch(conv, pdf_path: Path, batch: list[int], tmp: Path) -> dict[int, DoclingPage]:
    results: dict[int, DoclingPage] = {}
    sub = tmp / f"pages_{batch[0]}_{batch[-1]}_{threading.get_ident()}.pdf"
    started = time.perf_counter()
    try:
        _write_subset(pdf_path, batch, sub)
        res = conv.convert(sub, raises_on_error=False)
        document = res.document
        conf = getattr(res, "confidence", None)
        for internal, original in enumerate(batch, start=1):
            if internal not in document.pages:
                results[original] = DoclingPage(error="docling returned no page")
                continue
            page = _page_items(document, internal, original)
            scores = {}
            if conf is not None and getattr(conf, "pages", None):
                pc = conf.pages.get(internal - 1) or conf.pages.get(internal)
                if pc is not None:
                    scores = {
                        k: float(getattr(pc, k).value if hasattr(getattr(pc, k), "value") else getattr(pc, k))
                        for k in ("parse_score", "layout_score", "table_score", "ocr_score")
                        if getattr(pc, k, None) is not None
                    }
            page.scores = {k: v for k, v in scores.items() if v == v}  # drop NaN
            results[original] = page
    except Exception as exc:  # one bad batch must not lose the others
        logger.warning("docling failed on pages %s: %s", batch, exc)
        for original in batch:
            results[original] = DoclingPage(error=f"{type(exc).__name__}: {exc}")
    finally:
        elapsed = (time.perf_counter() - started) / max(1, len(batch))
        for original in batch:
            if original in results:
                results[original].scores.setdefault("seconds", elapsed)
        try:
            sub.unlink(missing_ok=True)
        except OSError:  # Windows: still open; the temp folder is removed later
            pass
        gc.collect()
    return results


def convert_pages(
    pdf_path: Path,
    table_pages: list[int],
    ocr_pages: list[int],
    *,
    on_page_done: Callable[[int], None] | None = None,
    lanes: int | None = None,
) -> tuple[dict[int, DoclingPage], dict[int, DoclingPage]]:
    """Run Docling on the table pages (no OCR) and the scanned pages (OCR).

    Returns ``(table_results, ocr_results)`` keyed by original page number.
    ``on_page_done`` is called once per finished page, from a worker thread.
    """
    tables: dict[int, DoclingPage] = {}
    ocrs: dict[int, DoclingPage] = {}
    if not table_pages and not ocr_pages:
        return tables, ocrs
    want_lanes = lanes or _dev.lanes()
    work: queue.Queue = queue.Queue()
    # Scans first: they are the slowest pages, so lanes finish closer together.
    for ocr, pages in ((True, ocr_pages), (False, table_pages)):
        # Small page sets are split so that every lane gets a share.
        step = max(1, min(_batch_size(), -(-len(pages) // want_lanes)))
        for i in range(0, len(pages), step):
            work.put((ocr, pages[i : i + step]))
    n_lanes = max(1, min(want_lanes, work.qsize()))
    lock = threading.Lock()
    errors: list[BaseException] = []

    def lane(index: int, tmp: Path) -> None:
        while True:
            try:
                ocr, batch = work.get_nowait()
            except queue.Empty:
                return
            try:
                out = _convert_batch(converter(ocr, index), pdf_path, batch, tmp)
            except BaseException as exc:  # e.g. a model failed to load
                errors.append(exc)
                out = {p: DoclingPage(error=f"{type(exc).__name__}: {exc}") for p in batch}
            with lock:
                (ocrs if ocr else tables).update(out)
            if on_page_done is not None:
                for p in batch:
                    on_page_done(p)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        if n_lanes == 1:
            lane(0, Path(tmp))
        else:
            threads = [threading.Thread(target=lane, args=(i, Path(tmp)), daemon=True) for i in range(n_lanes)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
    if errors:
        logger.warning("docling lane errors: %s", errors[0])
    return tables, ocrs
