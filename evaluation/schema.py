"""Golden-set records and loaders.

A golden set lives in ``evaluation/golden/<version>/``:

* ``documents.json``  - the documents, identified by file name and SHA-256
* ``figures.jsonl``   - key figures: value, sign, scale, page and box
* ``questions.jsonl`` - questions with gold answers and gold pages

PDFs are not committed (``data/`` is git-ignored); the SHA-256 makes sure a
result is only ever scored against the exact file the gold was drawn from.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

GOLDEN_ROOT = Path(__file__).resolve().parent / "golden"


class DocClass(str, Enum):
    ANNUAL_REPORT = "A_annual_report"
    SCANNED = "B_scanned"
    MIXED_TECHNICAL = "C_mixed_technical"
    TABLE_HEAVY = "D_table_heavy"
    AMHARIC_SCANNED = "E_amharic_scanned"


class GoldSource(str, Enum):
    TEXT_LAYER = "text_layer"  # read from the PDF's own text layer (exact)
    VISUAL = "visual"  # read by eye from a rendered page image


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"  # checked by a person against the page
    CORRECTED = "corrected"  # a person fixed the draft
    REJECTED = "rejected"  # unusable; excluded from scoring


class GoldDocument(BaseModel):
    doc_key: str = Field(description="Short stable id used across the golden set")
    file_name: str
    sha256: str
    pages: int
    doc_class: DocClass
    language: str = "en"
    title: str = Field(description="How a person would name the document in a question")
    notes: str = ""


class GoldFigure(BaseModel):
    figure_id: str
    doc_key: str
    page: int = Field(ge=1, description="1-indexed physical PDF page")
    row_label: str
    column_label: str = ""
    value_text: str = Field(description="The number exactly as printed")
    value: float = Field(description="Signed value as printed, before scale")
    scale: float = Field(default=1.0, description="Multiplier stated by the table, e.g. 1e6")
    unit: str = Field(default="", description="Currency or unit, e.g. ETB, %, count")
    period: str = ""
    bbox: list[float] | None = Field(
        default=None, description="[x0, top, x1, bottom] in PDF points, top-left origin"
    )
    table_title: str = ""
    source: GoldSource = GoldSource.TEXT_LAYER
    review: ReviewStatus = ReviewStatus.DRAFT
    review_note: str = ""

    @property
    def absolute_value(self) -> float:
        return self.value * self.scale


class QuestionType(str, Enum):
    LOOKUP_NUMBER = "lookup_number"
    CHANGE_PERCENT = "change_percent"
    LIST = "list"
    UNANSWERABLE = "unanswerable"


class GoldQuestion(BaseModel):
    question_id: str
    doc_key: str
    question: str
    qtype: QuestionType
    gold_value: float | None = Field(default=None, description="Absolute value after scale")
    gold_value_raw: float | None = Field(default=None, description="Value as printed")
    gold_is_percent: bool = False
    tolerance: float = Field(default=0.005, description="Relative tolerance for numbers")
    gold_items: list[str] = Field(default_factory=list, description="For list questions")
    gold_pages: list[int] = Field(default_factory=list)
    gold_answer_text: str = Field(default="", description="Human-readable gold answer")
    figure_ids: list[str] = Field(default_factory=list)
    review: ReviewStatus = ReviewStatus.DRAFT


class GoldenSet(BaseModel):
    version: str
    documents: list[GoldDocument]
    figures: list[GoldFigure]
    questions: list[GoldQuestion]

    def document(self, doc_key: str) -> GoldDocument:
        for d in self.documents:
            if d.doc_key == doc_key:
                return d
        raise KeyError(doc_key)

    def scored_figures(self) -> list[GoldFigure]:
        return [f for f in self.figures if f.review is not ReviewStatus.REJECTED]

    def scored_questions(self) -> list[GoldQuestion]:
        return [q for q in self.questions if q.review is not ReviewStatus.REJECTED]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[BaseModel]) -> None:
    path.write_text(
        "".join(r.model_dump_json() + "\n" for r in rows),
        encoding="utf-8",
    )


def golden_dir(version: str) -> Path:
    return GOLDEN_ROOT / version


def load_golden(version: str = "v1") -> GoldenSet:
    root = golden_dir(version)
    docs = json.loads((root / "documents.json").read_text(encoding="utf-8"))
    return GoldenSet(
        version=version,
        documents=[GoldDocument.model_validate(d) for d in docs],
        figures=[GoldFigure.model_validate(r) for r in _read_jsonl(root / "figures.jsonl")],
        questions=[GoldQuestion.model_validate(r) for r in _read_jsonl(root / "questions.jsonl")],
    )


def save_golden(golden: GoldenSet) -> None:
    root = golden_dir(golden.version)
    root.mkdir(parents=True, exist_ok=True)
    (root / "documents.json").write_text(
        json.dumps([d.model_dump(mode="json") for d in golden.documents], indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    _write_jsonl(root / "figures.jsonl", golden.figures)
    _write_jsonl(root / "questions.jsonl", golden.questions)
