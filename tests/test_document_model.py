"""Offline tests for the V2 structured document model, text-layer reader and renderer."""

from __future__ import annotations

from src.document import extract as ex
from src.document.model import BBox, Block, BlockType, DocumentModel, Page, PageQuality, Table, TableCell
from src.document.render import render_markdown
from src.document.text_layer import (
    Line,
    TextLayerPage,
    Word,
    _merge_fragments,
    _reading_order,
    _segments,
    _y_lines,
    blocks_from_lines,
    garbled_ratio,
    looks_like_table_page,
    text_in_box,
)


def W(text, x0, top, x1=None, size=10.0, bold=False):
    return Word(text, x0, top, x1 if x1 is not None else x0 + 6 * len(text), top + 10, size, bold)


def _tl(words, checks=None):
    lines = [s for ln in _y_lines(words) for s in _segments(ln, 14.0)]
    base = {"chars": sum(len(w.text) for w in words), "cid_glyphs": 0, "replacement_chars": 0, "doubled_runs": 0, "ethiopic_ratio": 0.0}
    base.update(checks or {})
    return TextLayerPage(words=words, lines=_reading_order(lines, 600), char_count=base["chars"], body_size=10.0, checks=base)


# --- Text layer -------------------------------------------------------------


def test_split_number_runs_are_merged():
    merged = _merge_fragments([W("3", 324, 10, 329), W("9,480,469", 329.3, 10)])
    assert [w.text for w in merged] == ["39,480,469"]


def test_two_columns_are_read_column_by_column():
    words = []
    for i in range(8):
        y = 100 + 14 * i
        words += [W("Left", 50, y), W(f"L{i}", 80, y), W("Right", 330, y), W(f"R{i}", 370, y)]
    tl = _tl(words)
    order = [ln.text for ln in tl.lines]
    assert order[:8] == [f"Left L{i}" for i in range(8)]
    assert order[8:] == [f"Right R{i}" for i in range(8)]


def test_table_rows_are_not_split_into_columns():
    # numbers separated by wide gaps belong to one row, not to separate columns
    line = [W("Vehicles", 80, 100), W("9,002.46", 330, 100), W("22,996.62", 470, 100)]
    assert len(_segments(line, 14.0)) == 1


def test_headings_from_font_size_and_paragraph_breaks():
    lines = [
        Line([W("Chapter", 50, 50, size=16), W("One", 110, 50, size=16)]),
        Line([W("First", 50, 80), W("sentence", 90, 80)]),
        Line([W("continues", 50, 92)]),
        Line([W("New", 50, 130), W("paragraph.", 80, 130)]),
    ]
    blocks = blocks_from_lines(lines, 1, 10.0, {16.0: 1})
    assert blocks[0].type is BlockType.HEADING and blocks[0].level == 1
    assert [b.text for b in blocks[1:]] == ["First sentence continues", "New paragraph."]


def test_table_page_detection_and_garble():
    rows = [[W("Item", 50, 100 + 15 * i), W("1,234", 300, 100 + 15 * i), W("5,678", 400, 100 + 15 * i)] for i in range(5)]
    tl = _tl([w for r in rows for w in r])
    assert looks_like_table_page(tl)
    bad = _tl([W("x", 10, 10)], {"chars": 100, "cid_glyphs": 10})
    assert garbled_ratio(bad) > 0.5


def test_text_in_box_reads_words_inside_only():
    words = [W("Total", 50, 100), W("1,234", 120, 100), W("outside", 300, 300)]
    assert text_in_box(words, BBox(x0=40, top=95, x1=200, bottom=115)) == "Total 1,234"
    assert text_in_box(words, BBox(x0=500, top=500, x1=510, bottom=510)) is None


def test_bottom_left_boxes_convert_to_top_left():
    b = BBox.from_bottom_left(82, 756.67, 498, 730.13, 842.04)
    assert round(b.top, 1) == 85.4 and round(b.bottom, 1) == 111.9


# --- Routing and post-processing ---------------------------------------------


def test_route_by_page_signals():
    text_page = _tl([W("Plain", 50, 100), W("prose", 100, 100), W("only", 150, 100)] * 4)
    assert ex._route(text_page, 0.0) == "text"
    empty = _tl([], {"chars": 0})
    assert ex._route(empty, 0.9) == "ocr"
    rows = [[W("Item", 50, 100 + 15 * i), W("1,234", 300, 100 + 15 * i), W("5,678", 400, 100 + 15 * i)] for i in range(5)]
    assert ex._route(_tl([w for r in rows for w in r]), 0.0) == "docling"


def test_cells_are_reread_from_the_text_layer():
    table = Table(
        table_id="p1-t0", n_rows=1, n_cols=2,
        cells=[
            TableCell(row=0, col=0, text="Burglary", bbox=BBox(x0=40, top=95, x1=150, bottom=115)),
            TableCell(row=0, col=1, text="1 82,044", bbox=BBox(x0=290, top=95, x1=360, bottom=115)),
        ],
    )
    tl = _tl([W("Burglary", 50, 100), W("182,044", 300, 100)])
    fixed, share = ex._reread_table(table, tl)
    assert fixed.grid() == [["Burglary", "182,044"]] and share == 1.0
    assert fixed.cells[1].text_source == "text_layer"


def _page(n, blocks=(), tables=(), flags=()):
    return Page(
        number=n, width=600, height=800, blocks=list(blocks), tables=list(tables),
        quality=PageQuality(engine="text_layer", confidence=0.9, flags=list(flags)),
    )


def test_running_headers_are_marked_and_not_rendered():
    pages = [
        _page(i, [
            Block(block_id=f"p{i}-b0", type=BlockType.TEXT, text=f"Annual report {i}", bbox=BBox(x0=50, top=10, x1=300, bottom=20)),
            Block(block_id=f"p{i}-b1", type=BlockType.TEXT, text=f"Body {i}", bbox=BBox(x0=50, top=300, x1=300, bottom=320)),
        ])
        for i in range(1, 6)
    ]
    ex._mark_running_headers(pages)
    assert all(p.blocks[0].type is BlockType.PAGE_HEADER for p in pages)
    md = render_markdown(DocumentModel(doc_id="d", file_name="f.pdf", sha256="s", page_count=5, pages=pages))
    assert "Annual report" not in md and "Body 3" in md


def _table(tid, header, rows, top=600):
    cells = [TableCell(row=0, col=c, text=h, is_header=bool(header)) for c, h in enumerate(header or rows[0])]
    start = 1
    body = rows if header else rows[1:]
    cells += [TableCell(row=start + r, col=c, text=v) for r, row in enumerate(body) for c, v in enumerate(row)]
    n_rows = 1 + len(body)
    return Table(table_id=tid, n_rows=n_rows, n_cols=len(rows[0]), cells=cells, bbox=BBox(x0=50, top=top, x1=500, bottom=top + 100))


def test_continued_table_repeats_the_header_and_failed_pages_say_so():
    t1 = _table("p1-t0", ["Item", "2020", "2021"], [["A", "1", "2"]])
    t2 = _table("p2-t0", None, [["B", "3", "4"], ["C", "5", "6"]], top=40)
    pages = [
        _page(1, [Block(block_id="p1-b0", type=BlockType.TABLE, text="p1-t0")], [t1]),
        _page(2, [Block(block_id="p2-b0", type=BlockType.TABLE, text="p2-t0")], [t2]),
        _page(3, flags=["no text could be extracted from this page"]),
    ]
    ex._link_continued_tables(pages)
    assert pages[1].tables[0].continued_from == "p1-t0"
    md = render_markdown(DocumentModel(doc_id="d", file_name="f.pdf", sha256="s", page_count=3, pages=pages))
    page2 = md.split("<!-- page 2 -->")[1].split("<!-- page 3 -->")[0]
    assert page2.strip().startswith("| Item | 2020 | 2021 |")
    assert "| B | 3 | 4 |" in page2
    assert "<!-- page 3 failed: no text could be extracted from this page -->" in md


def test_ledger_has_one_row_per_page():
    pages = [_page(1), _page(2, flags=["x"])]
    pages[1].quality.needs_review = True
    model = DocumentModel(doc_id="d", file_name="f.pdf", sha256="s", page_count=2, pages=pages)
    ledger = model.ledger()
    assert [r["page"] for r in ledger] == [1, 2] and ledger[1]["needs_review"] and ledger[1]["flags"] == ["x"]


# --- M4: preview model and picture-only pages -------------------------------


def test_preview_model_reads_text_pages_and_leaves_scans_for_later():
    from pathlib import Path

    tl = _tl([W("Revenue", 50, 100), W("grew", 110, 100), W("strongly", 150, 100), W("this", 210, 100), W("year", 250, 100)])
    tri = ex.Triage(pdf_path=Path("r.pdf"), sha="a" * 64, n_pages=3)
    tri.routes = {1: "text", 2: "docling", 3: "ocr"}
    tri.layers = {1: tl, 2: tl}
    tri.sizes = {n: (600.0, 800.0) for n in (1, 2, 3)}
    model = ex.preview_model(tri)
    assert [p.number for p in model.pages] == [1, 2, 3]
    assert "Revenue" in model.pages[0].body_text() and "Revenue" in model.pages[1].body_text()
    assert model.pages[2].blocks == [] and model.pages[2].quality.engine == "none"
    assert model.extractor == "docmind-v2-preview"


def test_picture_only_page_is_rendered_as_failed_not_as_content():
    page = _page(1, blocks=[Block(block_id="p1-b0", type=BlockType.TEXT, text="MODMDODODOG")],
                 flags=["little or no readable text: picture-only page?"])
    md = render_markdown(DocumentModel(doc_id="d", file_name="f.pdf", sha256="s", page_count=1, pages=[page]))
    assert "<!-- page 1 failed: little or no readable text" in md


def test_extraction_runtime_dependencies_are_installed():
    """Docling imports OpenCV only when a page is converted, and does not declare it."""
    import importlib

    for name in ("cv2", "pypdfium2", "pdfplumber", "docling.document_converter", "docling.backend.pypdfium2_backend"):
        importlib.import_module(name)
