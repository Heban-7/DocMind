"""Citation boxes: the cell or text that prints the answer's figure, not the page."""

from __future__ import annotations

from src.document.model import BBox, Block, BlockType, DocumentModel, Page, PageQuality, Table, TableCell
from src.models.query import ToolName
from src.query.evidence import EvidenceHit
from src.query.locate import locate, model_beside
from src.query.provenance import assemble_provenance
from src.query.verify import verify_answer

H = 800.0


def _cell(row, col, text, x0, x1, top, header=False):
    return TableCell(row=row, col=col, text=text, bbox=BBox(x0=x0, top=top, x1=x1, bottom=top + 12), is_header=header)


def _model() -> DocumentModel:
    table = Table(
        table_id="p1-t0",
        bbox=BBox(x0=50, top=300, x1=550, bottom=400),
        n_rows=3,
        n_cols=3,
        cells=[
            _cell(0, 0, "", 50, 300, 300, True),
            _cell(0, 1, "2023", 320, 420, 300, True),
            _cell(0, 2, "2022", 440, 540, 300, True),
            _cell(1, 0, "Total liabilities", 50, 300, 320),
            _cell(1, 1, "8,100", 320, 420, 320),
            _cell(1, 2, "7,050", 440, 540, 320),
            _cell(2, 0, "Total assets", 50, 300, 340),
            _cell(2, 1, "11,760", 320, 420, 340),
            _cell(2, 2, "9,689", 440, 540, 340),
        ],
    )
    blocks = [
        Block(block_id="p1-b0", type=BlockType.TITLE, text="Statement of financial position", bbox=BBox(x0=50, top=60, x1=400, bottom=80)),
        Block(
            block_id="p1-b1",
            type=BlockType.TEXT,
            text="The Bank's deposits grew to Birr 1.2 trillion during the year, driven by savings accounts.",
            bbox=BBox(x0=50, top=100, x1=550, bottom=140),
        ),
        Block(block_id="p1-b2", type=BlockType.TABLE, text="p1-t0", bbox=table.bbox),
        Block(block_id="p1-b3", type=BlockType.PAGE_FOOTER, text="11,760 page 4", bbox=BBox(x0=50, top=760, x1=550, bottom=780)),
    ]
    page = Page(number=1, width=600, height=H, blocks=blocks, tables=[table], quality=PageQuality(engine="text_layer", confidence=1.0))
    return DocumentModel(doc_id="d1", file_name="r.pdf", sha256="x", page_count=1, pages=[page])


def test_box_is_the_value_cell_and_its_row_label():
    boxes, kind = locate(_model(), 1, numbers=["11,760"], context="Total assets were 11,760 in 2023.")
    assert kind == "cell"
    # value cell and the "Total assets" label, flipped to a bottom-left origin
    assert [(b.x0, b.y1) for b in boxes] == [(320, H - 340), (50, H - 340)]
    assert all(b.page_height == H for b in boxes)


def test_change_boxes_both_figures():
    boxes, kind = locate(_model(), 1, numbers=["9,689", "11,760"], context="Total assets rose from 9,689 to 11,760.")
    assert kind == "cell"
    assert {b.x0 for b in boxes} == {440, 320, 50}


def test_scaled_number_in_text_is_boxed_on_its_block():
    boxes, kind = locate(_model(), 1, numbers=["Birr 1.2 trillion"], context="Deposits grew to Birr 1.2 trillion.")
    assert kind == "block"  # a figure in running text: the block that prints it
    assert len(boxes) == 1 and boxes[0].x0 == 50 and boxes[0].y1 == H - 100


def test_passage_without_numbers_boxes_its_blocks():
    boxes, kind = locate(
        _model(), 1, excerpt="The Bank's deposits grew to Birr 1.2 trillion during the year, driven by savings accounts."
    )
    assert kind == "block" and len(boxes) == 1


def test_unknown_page_or_model_falls_back_to_page():
    assert locate(None, 1, numbers=["5"]) == ([], "page")
    assert locate(_model(), 9, numbers=["5"]) == ([], "page")
    assert locate(_model(), 1, numbers=["123,456"], context="x") == ([], "page")


def test_verifier_reports_which_evidence_prints_which_figure():
    check = verify_answer(
        "Total assets were 11,760 [E2]. Liabilities were 8,100 [E1].",
        ["Total liabilities 8,100 7,050", "Total assets 11,760 9,689"],
    )
    assert check.evidence_numbers == {2: ["11,760"], 1: ["8,100"]}
    assert "Total assets were 11,760" in check.evidence_claims[2][0]


def test_provenance_uses_the_model_beside_the_pdf(tmp_path):
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "source.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(600, H))
    c.drawString(60, 400, "Total assets 11,760 9,689")
    c.save()
    (tmp_path / "model.json").write_text(_model().model_dump_json(), encoding="utf-8")
    assert model_beside(pdf) is not None
    hit = EvidenceHit(
        tool=ToolName.SEMANTIC_SEARCH, document_name="r.pdf", doc_id="d1", page_number=1, content_hash="h",
        chunk_id="c1", excerpt="| Total assets | 11,760 | 9,689 |",
        extra={"claim_numbers": ["11,760"], "claim_text": "Total assets were 11,760."},
    )
    chain = assemble_provenance([hit], pdf_for=lambda _d: pdf)
    cite = chain.citations[0]
    assert cite.box_kind == "cell" and len(cite.boxes) == 2
    assert cite.bbox.x0 == 50 and cite.bbox.x1 == 420  # union of the label and the value
    # a hit from a document whose PDF is unknown is not boxed on another file
    other = hit.model_copy(update={"doc_id": "d2", "content_hash": "h2"})
    chain = assemble_provenance([other], pdf_path=pdf, pdf_for=lambda d: pdf if d == "d1" else None)
    assert chain.citations[0].box_kind == "page" and not chain.citations[0].bbox.is_resolved


def test_same_figure_twice_prefers_the_total_column():
    model = _model()
    t = model.pages[0].tables[0]
    t.cells[1].text, t.cells[2].text = "Non-Life", "Total"
    t.cells[5].text = "8,100"  # Total liabilities printed under both columns
    boxes, kind = locate(model, 1, numbers=["8,100"], context="Total liabilities were 8,100.")
    assert kind == "cell" and boxes[0].x0 == 440


def test_figure_on_the_next_page_of_a_passage_moves_the_citation():
    from src.query.locate import locate_on_pages

    model = _model()
    first = model.pages[0].model_copy(update={"number": 1, "tables": [], "blocks": model.pages[0].blocks[:1]})
    second = model.pages[0].model_copy(update={"number": 2})
    model = model.model_copy(update={"pages": [first, second], "page_count": 2})
    page, boxes, kind = locate_on_pages(model, [1, 2], numbers=["11,760"], context="Total assets were 11,760.")
    assert page == 2 and kind == "cell"


def test_a_day_in_a_date_is_not_boxed():
    check = verify_answer("Total assets were 11,760 at 30 June 2023 [E1].", ["Total assets 11,760 at 30 June 2023"])
    assert check.evidence_numbers == {1: ["11,760"]}

