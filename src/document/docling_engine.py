"""Docling for the pages that need layout analysis: tables and scans.

Only the selected pages are sent (as a small sub-PDF), the converter is built
once per process and reused, and every Docling item keeps its box. On digital
pages the caller replaces Docling's text with the PDF's own words inside each
box, so numbers are never broken by Docling's parser.
"""

from __future__ import annotations

import gc
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.config import (
    DOCLING_NUM_THREADS,
    DOCLING_PAGE_BATCH_CPU,
    DOCLING_PAGE_BATCH_GPU,
    EXTRACTION_DEVICE,
    OCR_LANGUAGES,
)
from src.document.model import BBox, Block, BlockType, Table, TableCell

logger = logging.getLogger("docmind.document.docling")

_CONVERTERS: dict[tuple[bool, str], object] = {}

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
    from src.extraction._docling_support import _resolve_device

    return _resolve_device(EXTRACTION_DEVICE)


def _ocr_options(is_gpu: bool):
    from docling.datamodel.pipeline_options import EasyOcrOptions, TesseractCliOcrOptions

    if shutil.which("tesseract"):
        return TesseractCliOcrOptions(lang=list(OCR_LANGUAGES), force_full_page_ocr=True), "tesseract"
    # Without Tesseract there is no Amharic OCR at all; pages are flagged by the caller.
    return EasyOcrOptions(lang=["en"], force_full_page_ocr=True, use_gpu=is_gpu), "easyocr"


def table_mode() -> str:
    import os

    return os.getenv("DOCMIND_V2_TABLE_MODE", "accurate").lower()


def converter(ocr: bool):
    """One converter per (ocr, table mode), built on first use and kept."""
    key = (ocr, table_mode())
    if key in _CONVERTERS:
        return _CONVERTERS[key]
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption

    device, is_gpu = _device()
    opts = PdfPipelineOptions()
    opts.accelerator_options = AcceleratorOptions(device=device, num_threads=DOCLING_NUM_THREADS)
    opts.do_ocr = ocr
    opts.do_table_structure = True
    opts.table_structure_options.mode = (
        TableFormerMode.ACCURATE if key[1] == "accurate" else TableFormerMode.FAST
    )
    if ocr:
        opts.ocr_options, engine = _ocr_options(is_gpu)
        logger.info("docling OCR engine: %s", engine)
    conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    _CONVERTERS[key] = conv
    return conv


def ocr_engine_name() -> str:
    return "tesseract" if shutil.which("tesseract") else "easyocr"


def _batch_size() -> int:
    _, is_gpu = _device()
    return max(1, DOCLING_PAGE_BATCH_GPU if is_gpu else DOCLING_PAGE_BATCH_CPU)


def _write_subset(src: Path, pages: list[int], out: Path) -> None:
    import pypdfium2 as pdfium

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


def convert_pages(pdf_path: Path, pages: list[int], *, ocr: bool) -> dict[int, DoclingPage]:
    """Run Docling on ``pages`` (1-indexed) and return items per original page."""
    results: dict[int, DoclingPage] = {}
    if not pages:
        return results
    conv = converter(ocr)
    step = _batch_size()
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(0, len(pages), step):
            batch = pages[i : i + step]
            sub = Path(tmp) / f"pages_{batch[0]}_{batch[-1]}.pdf"
            started = time.perf_counter()
            try:
                _write_subset(pdf_path, batch, sub)
                res = conv.convert(sub, raises_on_error=False)
                document = res.document
                scores = {}
                conf = getattr(res, "confidence", None)
                for internal, original in enumerate(batch, start=1):
                    if internal not in document.pages:
                        results[original] = DoclingPage(error="docling returned no page")
                        continue
                    page = _page_items(document, internal, original)
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
                gc.collect()
    return results
