"""Build golden set v1 from the corpus.

Step 1 (``documents``) writes ``documents.json``: the 25 documents with their
SHA-256 and page counts. Step 2 (``figures``) drafts figures from the text
layer and merges hand-entered figures (``manual_figures.json``). Step 3
(``questions``) generates questions from the figures.

Usage:
    python -m evaluation.draft.build_golden_v1 documents
    python -m evaluation.draft.build_golden_v1 figures
    python -m evaluation.draft.build_golden_v1 questions
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pypdfium2 as pdfium

from evaluation.schema import (
    DocClass,
    GoldDocument,
    GoldenSet,
    GoldFigure,
    GoldQuestion,
    GoldSource,
    QuestionType,
    ReviewStatus,
    golden_dir,
    load_golden,
    save_golden,
)

CORPUS_DIR = Path(os.getenv("DOCMIND_CORPUS_DIR", Path(__file__).resolve().parents[2] / "data" / "data"))
VERSION = "v1"

A, B, C, D, E = (
    DocClass.ANNUAL_REPORT,
    DocClass.SCANNED,
    DocClass.MIXED_TECHNICAL,
    DocClass.TABLE_HEAVY,
    DocClass.AMHARIC_SCANNED,
)

# doc_key, file name, class, language, how a person would name it in a question
DOCS: list[tuple[str, str, DocClass, str, str]] = [
    ("cbe_2023_24", "CBE ANNUAL REPORT 2023-24.pdf", A, "en", "the Commercial Bank of Ethiopia Annual Report 2023-24"),
    ("ethiore_2017", "Annual_Report_JUNE-2017.pdf", A, "en", "the Ethiopian Reinsurance annual report (June 2017 file)"),
    ("ets_2023_24", "ETS-Annual-Report-2023_2024.pdf", A, "en", "the EthSwitch Annual Report 2023/2024"),
    ("ethswitch_10th_2023_24", "EthSwitch-10th-Annual-Report-202324.pdf", A, "en", "the EthSwitch 10th Annual Report 2023/24"),
    ("ethswitch_2021_22", "ETHSWITCH-Annual-Report-202122.pdf", A, "en", "the EthSwitch Annual Report 2021/22"),
    ("cbe_2006_07", "CBE Annual Report 2006-7 .pdf", A, "en", "the Commercial Bank of Ethiopia Annual Report 2006-07"),
    ("ethiore_profile_2024_25", "Company_Profile_2024_25.pdf", A, "en", "the Ethiopian Reinsurance Company Profile 2024/25"),
    ("dbe_audit_2023", "Audit Report - 2023.pdf", B, "en", "the Development Bank of Ethiopia audit report 2023"),
    ("cbe_2010_11", "CBE Annual Report 2010-11.pdf", B, "en", "the Commercial Bank of Ethiopia Annual Report 2010-11"),
    ("cbe_2009_10", "CBE Annual Report 2009-10.pdf", B, "en", "the Commercial Bank of Ethiopia Annual Report 2009-10"),
    ("ethswitch_2019", "EthSwitch-Annual-Report-2019.pdf", B, "en", "the EthSwitch Annual Report 2019"),
    ("audited_fs_2021", "2021_Audited_Financial_Statement_Report.pdf", B, "en", "the 2021 audited financial statement report"),
    ("security_disclosure", "Security_Vulnerability_Disclosure_Standard_Procedure_1.pdf", B, "en", "the Security Vulnerability Disclosure Standard Procedure"),
    ("fta_survey_2022", "fta_performance_survey_final_report_2022.pdf", C, "en", "the Financial Transparency and Accountability performance survey final report 2022"),
    ("pharma_2019", "20191010_Pharmaceutical-Manufacturing-Opportunites-in-Ethiopia_VF.pdf", C, "en", "the Pharmaceutical Manufacturing Opportunities in Ethiopia report"),
    ("ethiore_2019", "Annual_Report_JUNE-2019.pdf", C, "en", "the Ethiopian Reinsurance annual report (June 2019 file)"),
    ("cbe_2012_13", "CBE Annual Report 2012-13.pdf", C, "en", "the Commercial Bank of Ethiopia Annual Report 2012-13"),
    ("tax_exp_2021_22", "tax_expenditure_ethiopia_2021_22.pdf", D, "en", "the Ethiopia Import Tax Expenditure Report FY 2018/19-2020/21"),
    ("tax_exp_sample", "Sample - Ethiopia Tax Expenditure Report.pdf", D, "en", "the 20-page sample of the Ethiopia Import Tax Expenditure Report"),
    ("cpi_2025_08", "Consumer Price Index August 2025.pdf", D, "en", "the Consumer Price Index bulletin for August 2025"),
    ("cpi_2025_03", "Consumer Price Index March 2025.pdf", D, "en", "the Consumer Price Index bulletin for March 2025"),
    ("cpi_2025_06", "Consumer Price Index June 2025.pdf", D, "en", "the Consumer Price Index bulletin for June 2025"),
    ("am_audit_findings", "2013-E.C-Audit-finding-information.pdf", E, "am", "the 2013 E.C. audit finding information document"),
    ("am_procurement", "2013-E.C-Procurement-information.pdf", E, "am", "the 2013 E.C. procurement information document"),
    ("am_budget", "2013-E.C-Assigned-regular-budget-and-expense.pdf", E, "am", "the 2013 E.C. assigned regular budget and expense document"),
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def page_count(path: Path) -> int:
    doc = pdfium.PdfDocument(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


def build_documents() -> list[GoldDocument]:
    docs = []
    for key, name, cls, lang, title in DOCS:
        path = CORPUS_DIR / name
        docs.append(
            GoldDocument(
                doc_key=key,
                file_name=name,
                sha256=sha256_of(path),
                pages=page_count(path),
                doc_class=cls,
                language=lang,
                title=title,
            )
        )
    return docs


def cmd_documents() -> None:
    root = golden_dir(VERSION)
    root.mkdir(parents=True, exist_ok=True)
    try:
        golden = load_golden(VERSION)
        golden.documents = build_documents()
    except FileNotFoundError:
        golden = GoldenSet(version=VERSION, documents=build_documents(), figures=[], questions=[])
    save_golden(golden)
    print(f"{len(golden.documents)} documents, {sum(d.pages for d in golden.documents)} pages")


# --- Figures --------------------------------------------------------------------

DRAFTS_DIR = Path(__file__).resolve().parents[1] / "runs" / "drafts"
FIGURES_PER_DOC = 10
TEXT_LAYER_CLASSES = {A, C, D}
SEED = 20261123


def _draft_to_gold(doc_key: str, n: int, d) -> GoldFigure:
    period = d.column_label if d.header_kind == "period" else ""
    note = f"scale: {d.scale_note}; source line: {d.source_line}"
    return GoldFigure(
        figure_id=f"{doc_key}-f{n:02d}",
        doc_key=doc_key,
        page=d.page,
        row_label=d.row_label,
        column_label=d.column_label,
        value_text=d.value_text,
        value=d.value,
        scale=d.scale,
        unit=d.unit,
        period=period,
        bbox=d.bbox,
        table_title=d.table_title,
        source=GoldSource.TEXT_LAYER,
        review_note=note,
    )


def cmd_figures() -> None:
    from dataclasses import asdict

    from evaluation.draft.text_layer_figures import draft_document, select

    golden = load_golden(VERSION)
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    figures: list[GoldFigure] = []
    for doc in golden.documents:
        if doc.doc_class not in TEXT_LAYER_CLASSES:
            continue
        drafts = draft_document(CORPUS_DIR / doc.file_name)
        (DRAFTS_DIR / f"{doc.doc_key}.jsonl").write_text(
            "".join(json.dumps(asdict(d), ensure_ascii=False) + "\n" for d in drafts), encoding="utf-8"
        )
        chosen = select(drafts, FIGURES_PER_DOC, SEED)
        figures.extend(_draft_to_gold(doc.doc_key, i + 1, d) for i, d in enumerate(chosen))
        print(f"{doc.doc_key}: {len(drafts)} candidates, {len(chosen)} drafted")
    manual_path = golden_dir(VERSION) / "manual_figures.json"
    if manual_path.exists():
        manual = [GoldFigure.model_validate(r) for r in json.loads(manual_path.read_text(encoding="utf-8"))]
        figures.extend(manual)
        print(f"manual figures: {len(manual)}")
    golden.figures = figures
    save_golden(golden)
    print(f"total figures: {len(figures)}")


# --- Curation and questions ---------------------------------------------------------

# Drafts a reviewer would reject on sight; kept in the set as REJECTED with the reason.
REJECT_RULES: list[tuple[str, str, str]] = [
    ("ets_2023_24", "GNreots", "garbled text layer (overlapping characters)"),
    ("ets_2023_24", "leave payable", "column header '2017' is not the period of this value"),
    ("ethiore_2017", "Nib Internatio", "label cut off in the text layer"),
    ("fta_survey_2022", "B The teachers", "'99' is a survey code for 'don't know', not a figure"),
    ("fta_survey_2022", "A The office", "'99' is a survey code for 'don't know', not a figure"),
    ("fta_survey_2022", "B Staff are", "'99' is a survey code for 'don't know', not a figure"),
]
# Table drafts for these were too noisy; their prose figures are entered by hand.
MANUAL_ONLY_DOCS = {"cpi_2025_08", "cpi_2025_03", "cpi_2025_06"}
QUESTIONS_PER_DOC = 6


def _curate(figures: list[GoldFigure]) -> list[GoldFigure]:
    out = []
    for f in figures:
        if f.doc_key in MANUAL_ONLY_DOCS and f.figure_id.rsplit("-", 1)[-1].startswith("f"):
            continue
        for doc_key, prefix, reason in REJECT_RULES:
            if f.doc_key == doc_key and f.row_label.startswith(prefix) and f.review is not ReviewStatus.REJECTED:
                f.review = ReviewStatus.REJECTED
                f.review_note = f"rejected: {reason}. " + f.review_note
        out.append(f)
    return out


_DOUBLED = re.compile(r"(\w)\1(\w)\2(\w)\3")  # "NNuummbbeerr": text drawn twice


def _suspicious_label(doc_key: str, label: str) -> bool:
    if _DOUBLED.search(label):
        return True
    return any(doc_key == d and label.startswith(p) for d, p, _ in REJECT_RULES)


def _short_title(table_title: str) -> str:
    m = re.match(r"^((?:Table|TABLE|Schedule)\s+[A-Z]?\d+(?:\.\d+)?)", table_title)
    return m.group(1) if m else table_title[:60]


def _lookup_question(doc: GoldDocument, f: GoldFigure) -> str:
    where = f" in {_short_title(f.table_title)}" if f.table_title else ""
    if f.period:
        return f"According to {doc.title}, what is the figure for “{f.row_label}” for {f.column_label}{where}?"
    return f"According to {doc.title}, what is the “{f.column_label}” figure for “{f.row_label}”{where}?"


def _load_drafts(doc_key: str):
    from evaluation.draft.text_layer_figures import DraftFigure

    path = DRAFTS_DIR / f"{doc_key}.jsonl"
    if not path.exists():
        return []
    return [DraftFigure(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _change_pair(doc_key: str):
    """Two period values on one table row (older, newer) for a % change question."""
    from evaluation.draft.text_layer_figures import _GENERIC_LABEL

    rows: dict[tuple[int, int], list] = {}
    for d in _load_drafts(doc_key):
        if d.header_kind != "period" or d.unit == "%" or d.value == 0 or _GENERIC_LABEL.match(d.row_label):
            continue
        if _suspicious_label(doc_key, d.row_label):
            continue
        rows.setdefault((d.page, round(d.bbox[1])), []).append(d)
    for key in sorted(rows):
        cells = {d.column_label: d for d in rows[key]}
        if len(cells) >= 2:
            periods = sorted(cells)
            return cells[periods[0]], cells[periods[-1]]
    return None


def _list_table(doc_key: str):
    from evaluation.draft.text_layer_figures import _GENERIC_LABEL

    tables: dict[tuple[int, str], list[str]] = {}
    for d in _load_drafts(doc_key):
        if not d.table_title or _GENERIC_LABEL.match(d.row_label):
            continue
        labels = tables.setdefault((d.page, d.table_title), [])
        if d.row_label not in labels:
            labels.append(d.row_label)
    for (page, title), labels in sorted(tables.items()):
        if 4 <= len(labels) <= 12:
            return page, title, labels
    return None


def cmd_questions() -> None:
    from collections import Counter

    golden = load_golden(VERSION)
    golden.figures = [f for f in _curate(golden.figures) if not f.figure_id.rsplit("-", 1)[-1].startswith("c")]
    manual_path = golden_dir(VERSION) / "manual_questions.json"
    questions = [GoldQuestion.model_validate(r) for r in json.loads(manual_path.read_text(encoding="utf-8"))]
    have = Counter(q.doc_key for q in questions)
    extra_figures: list[GoldFigure] = []
    for doc in golden.documents:
        if doc.doc_class not in TEXT_LAYER_CLASSES or doc.doc_key in MANUAL_ONLY_DOCS:
            continue
        budget = QUESTIONS_PER_DOC - have[doc.doc_key]
        if budget <= 0:
            continue
        drafted = [
            f for f in golden.figures
            if f.doc_key == doc.doc_key and f.review is not ReviewStatus.REJECTED
            and f.figure_id.rsplit("-", 1)[-1].startswith("f")
        ]
        new: list[GoldQuestion] = []

        def qid() -> str:
            return f"{doc.doc_key}-q{have[doc.doc_key] + len(new) + 1:02d}"

        for f in drafted[: max(1, budget - 3)]:
            new.append(GoldQuestion(
                question_id=qid(), doc_key=doc.doc_key, question=_lookup_question(doc, f),
                qtype=QuestionType.LOOKUP_NUMBER, gold_value=f.absolute_value, gold_value_raw=f.value,
                gold_is_percent=f.unit == "%", gold_pages=[f.page], figure_ids=[f.figure_id],
                gold_answer_text=f.value_text,
            ))
        pair = _change_pair(doc.doc_key)
        if pair and len(new) < budget:
            old, newer = pair
            ids = []
            for tag, d in (("c1", old), ("c2", newer)):
                gf = _draft_to_gold(doc.doc_key, 0, d)
                gf.figure_id = f"{doc.doc_key}-{tag}"
                extra_figures.append(gf)
                ids.append(gf.figure_id)
            pct = (newer.value - old.value) / abs(old.value) * 100
            where = f" in {_short_title(newer.table_title)}" if newer.table_title else ""
            new.append(GoldQuestion(
                question_id=qid(), doc_key=doc.doc_key,
                question=(f"According to {doc.title}, by what percentage did “{newer.row_label}” "
                          f"change from {old.column_label} to {newer.column_label}{where}?"),
                qtype=QuestionType.CHANGE_PERCENT, gold_value=round(pct, 2), gold_value_raw=round(pct, 2),
                gold_is_percent=True, tolerance=0.02, gold_pages=sorted({old.page, newer.page}), figure_ids=ids,
                gold_answer_text=f"{pct:+.1f}% ({old.value_text} to {newer.value_text})",
            ))
        table = _list_table(doc.doc_key)
        if table and len(new) < budget:
            page, title, labels = table
            new.append(GoldQuestion(
                question_id=qid(), doc_key=doc.doc_key,
                question=f"Which line items are listed in {_short_title(title)} of {doc.title}?",
                qtype=QuestionType.LIST, gold_items=labels, gold_pages=[page], gold_answer_text="; ".join(labels),
            ))
        if drafted and len(new) < budget:
            f = drafted[0]
            new.append(GoldQuestion(
                question_id=qid(), doc_key=doc.doc_key,
                question=f"According to {doc.title}, what was the figure for “{f.row_label}” in 2035?",
                qtype=QuestionType.UNANSWERABLE,
                gold_answer_text="The document has no 2035 figures; the system should say so.",
            ))
        # Fill any remaining budget with more lookups.
        for f in drafted[max(1, budget - 3):]:
            if len(new) >= budget:
                break
            new.append(GoldQuestion(
                question_id=qid(), doc_key=doc.doc_key, question=_lookup_question(doc, f),
                qtype=QuestionType.LOOKUP_NUMBER, gold_value=f.absolute_value, gold_value_raw=f.value,
                gold_is_percent=f.unit == "%", gold_pages=[f.page], figure_ids=[f.figure_id],
                gold_answer_text=f.value_text,
            ))
        questions.extend(new)
    golden.figures = golden.figures + extra_figures
    golden.questions = questions
    save_golden(golden)
    rejected = sum(f.review is ReviewStatus.REJECTED for f in golden.figures)
    print(f"figures: {len(golden.figures)} ({rejected} rejected)")
    print(f"questions: {len(questions)}", dict(Counter(q.qtype.value for q in questions)))


COMMANDS = {"documents": cmd_documents, "figures": cmd_figures, "questions": cmd_questions}

if __name__ == "__main__":
    COMMANDS[sys.argv[1]]()
