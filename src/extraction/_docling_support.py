"""
Shared Docling plumbing for the layout-aware and vision-augmented tiers.

Centralizes three concerns so the engines stay thin:
  * Device acceleration  -- auto-selects CUDA/MPS/CPU (production-portable).
  * Memory-safe batching -- device-aware page batches (big on GPU, safe on CPU).
  * OCR engine selection -- Tesseract (Amharic-capable) or EasyOCR (Latin only).
"""

from __future__ import annotations

import gc
import shutil
import tempfile
from pathlib import Path

from src.config import (
    DOCLING_NUM_THREADS,
    DOCLING_PAGE_BATCH_CPU,
    DOCLING_PAGE_BATCH_GPU,
    DOCLING_TABLE_MODE,
    EXTRACTION_DEVICE,
    OCR_ENGINE,
    OCR_LANGUAGES,
)


def _count_pages(path: Path) -> int:
    """Cheaply count pages without loading the heavy Docling stack."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


def _write_chunk(src_path: Path, start: int, end: int, out_path: Path) -> None:
    """Write pages [start, end] (1-indexed, inclusive) of a PDF to out_path.

    Splitting the document means each Docling call parses only a handful of
    pages -- avoiding the huge cost of re-parsing the WHOLE PDF per batch, while
    keeping each conversion small enough to stay accurate and memory-safe.
    """
    import pypdfium2 as pdfium

    src = pdfium.PdfDocument(str(src_path))
    dst = pdfium.PdfDocument.new()
    try:
        dst.import_pages(src, list(range(start - 1, end)))  # 0-indexed
        dst.save(str(out_path))
    finally:
        dst.close()
        src.close()


def _resolve_device(configured: str):
    """Map the configured device to a Docling AcceleratorDevice.

    "auto" -> CUDA if a GPU is visible, else Apple MPS, else CPU. This is what
    keeps the pipeline fast on a GPU host yet correct on a CPU-only server.
    Returns (AcceleratorDevice, is_gpu: bool).
    """
    from docling.datamodel.accelerator_options import AcceleratorDevice

    choice = (configured or "auto").lower()
    if choice == "cpu":
        return AcceleratorDevice.CPU, False
    if choice == "cuda":
        return AcceleratorDevice.CUDA, True
    if choice == "mps":
        return AcceleratorDevice.MPS, True

    # auto-detect
    try:
        import torch

        if torch.cuda.is_available():
            return AcceleratorDevice.CUDA, True
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return AcceleratorDevice.MPS, True
    except Exception:
        pass
    return AcceleratorDevice.CPU, False


def _tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _select_ocr_engine() -> str:
    """Decide which OCR engine to use: 'tesseract' or 'easyocr'."""
    choice = (OCR_ENGINE or "auto").lower()
    if choice in ("tesseract", "easyocr"):
        return choice
    # auto: prefer Tesseract (it can read Amharic) when it's installed.
    return "tesseract" if _tesseract_available() else "easyocr"


def _build_ocr_options(is_gpu: bool):
    """Construct OCR options for the selected engine.

    Tesseract is required for Amharic (EasyOCR has no Ethiopic model). If
    Tesseract is requested/auto-selected but not installed, we fall back to
    EasyOCR with a clear-eyed limitation (Latin scripts only).
    """
    from docling.datamodel.pipeline_options import (
        EasyOcrOptions,
        TesseractCliOcrOptions,
    )

    engine = _select_ocr_engine()

    if engine == "tesseract" and _tesseract_available():
        # e.g. lang=["amh", "eng"]; full-page OCR is correct for true scans.
        return TesseractCliOcrOptions(
            lang=list(OCR_LANGUAGES), force_full_page_ocr=True
        )

    # EasyOCR path: it cannot read Amharic, so restrict to Latin languages to
    # avoid nonsense output on Ethiopic pages.
    latin_langs = [lang_code for lang_code in ("en",)]
    return EasyOcrOptions(
        lang=latin_langs, force_full_page_ocr=True, use_gpu=is_gpu
    )


def _export_pages_with_markers(document, start: int, end: int) -> list[str]:
    """Export one Markdown section per physical page with provenance markers.

    Docling assigns page numbers 1..N *within the batch PDF* we converted. We
    map those back to the original document's page indices (``start``..``end``)
    and prepend ``<!-- page N -->`` before each page's markdown so the chunker
    can stamp accurate ``page_numbers`` on every LDU.
    """
    parts: list[str] = []
    batch_len = end - start + 1
    for internal in range(1, batch_len + 1):
        original_page = start + internal - 1
        page_md = document.export_to_markdown(page_no=internal).strip()
        if not page_md:
            continue
        parts.append(f"<!-- page {original_page} -->")
        parts.append(page_md)
    return parts


def convert_to_markdown(
    file_path: str,
    *,
    do_ocr: bool,
    max_pages: int | None = None,
    batch_size: int | None = None,
) -> str:
    """Convert a PDF to structure-preserving Markdown via Docling.

    Args:
        file_path: path to the PDF.
        do_ocr: False for digital docs (Strategy B); True to "read" pixels on
            scanned/image documents (Strategy C's OCR fallback).
        max_pages: process at most this many leading pages (None = whole doc).
        batch_size: pages per Docling call; None -> device-aware default
            (GPU batch on a GPU, 1 on CPU to stay memory-safe).

    Note: Docling/EasyOCR (and the heavy PyTorch stack) are imported lazily
    *here* so the cheap fast-text path never pays to load those backends.
    """
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableFormerMode,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No PDF found at '{path}'.")

    device, is_gpu = _resolve_device(EXTRACTION_DEVICE)

    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options = AcceleratorOptions(
        device=device, num_threads=DOCLING_NUM_THREADS
    )
    pipeline_options.do_ocr = do_ocr
    pipeline_options.table_structure_options.mode = (
        TableFormerMode.ACCURATE
        if DOCLING_TABLE_MODE.lower() == "accurate"
        else TableFormerMode.FAST
    )
    if do_ocr:
        pipeline_options.ocr_options = _build_ocr_options(is_gpu)

    # Build the converter ONCE (models load once) and reuse it per batch.
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    if batch_size is None:
        batch_size = DOCLING_PAGE_BATCH_GPU if is_gpu else DOCLING_PAGE_BATCH_CPU

    total_pages = _count_pages(path)
    last_page = total_pages if max_pages is None else min(max_pages, total_pages)
    step = max(1, batch_size)

    parts: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for start in range(1, last_page + 1, step):
            end = min(start + step - 1, last_page)
            chunk_path = tmp_dir / f"chunk_{start:05d}_{end:05d}.pdf"
            try:
                _write_chunk(path, start, end, chunk_path)
                result = converter.convert(chunk_path)
                parts.extend(
                    _export_pages_with_markers(result.document, start, end)
                )
            except Exception as exc:  # keep going; one bad chunk shouldn't kill all
                parts.append(f"<!-- pages {start}-{end} failed: {exc} -->")
            finally:
                gc.collect()

    return "\n\n".join(p for p in parts if p).strip()
