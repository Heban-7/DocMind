"""Export the golden set to a review sheet, and import a person's decisions.

    python -m evaluation.review export            # writes golden/v1/review_sheet.csv
    python -m evaluation.review import <sheet.csv> # applies the "status" column

The sheet has one row per figure and per question. A reviewer opens the PDF
at the given page, checks the row, and fills ``status`` with one of
``confirmed``, ``corrected`` (and fills ``corrected_value``) or ``rejected``
(and says why in ``comment``). Rows marked ``sample = yes`` are the ones to
check first: every Amharic item plus a fixed 20% sample of the rest.
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

from evaluation.numbers import parse_number
from evaluation.schema import GoldenSet, ReviewStatus, golden_dir, load_golden, save_golden

COLUMNS = [
    "sample", "kind", "id", "document", "page", "what", "value_or_answer", "how_it_was_read",
    "status", "corrected_value", "comment",
]
SAMPLE_SHARE = 0.2
SEED = 20261123


def _sample_ids(golden: GoldenSet) -> set[str]:
    amharic = {d.doc_key for d in golden.documents if d.language == "am"}
    ids = [f.figure_id for f in golden.figures] + [q.question_id for q in golden.questions]
    doc_of = {f.figure_id: f.doc_key for f in golden.figures} | {q.question_id: q.doc_key for q in golden.questions}
    must = {i for i in ids if doc_of[i] in amharic}
    rest = sorted(i for i in ids if i not in must)
    rng = random.Random(SEED)
    return must | set(rng.sample(rest, round(len(rest) * SAMPLE_SHARE)))


def export_sheet(version: str = "v1") -> Path:
    golden = load_golden(version)
    sample = _sample_ids(golden)
    files = {d.doc_key: d.file_name for d in golden.documents}
    rows = []
    for f in golden.figures:
        what = f.row_label + (f" | column: {f.column_label}" if f.column_label else "")
        if f.table_title:
            what += f" | table: {f.table_title[:80]}"
        scale = "" if f.scale == 1 else f" (x{f.scale:g} stated scale)"
        rows.append({
            "sample": "yes" if f.figure_id in sample else "",
            "kind": "figure",
            "id": f.figure_id,
            "document": files[f.doc_key],
            "page": f.page,
            "what": what,
            "value_or_answer": f"{f.value_text}{scale}",
            "how_it_was_read": f"{f.source.value}; {f.review_note}"[:300],
            "status": "" if f.review is ReviewStatus.DRAFT else f.review.value,
            "corrected_value": "",
            "comment": "",
        })
    for q in golden.questions:
        rows.append({
            "sample": "yes" if q.question_id in sample else "",
            "kind": f"question ({q.qtype.value})",
            "id": q.question_id,
            "document": files[q.doc_key],
            "page": ", ".join(str(p) for p in q.gold_pages),
            "what": q.question,
            "value_or_answer": q.gold_answer_text,
            "how_it_was_read": "from figures " + ", ".join(q.figure_ids) if q.figure_ids else "written by hand",
            "status": "" if q.review is ReviewStatus.DRAFT else q.review.value,
            "corrected_value": "",
            "comment": "",
        })
    rows.sort(key=lambda r: (r["sample"] != "yes", r["document"], r["kind"], r["id"]))
    path = golden_dir(version) / "review_sheet.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:  # BOM so Excel shows Amharic correctly
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"{path}: {len(rows)} rows, {sum(r['sample'] == 'yes' for r in rows)} in the review sample")
    return path


def import_sheet(sheet: Path, version: str = "v1") -> None:
    golden = load_golden(version)
    figs = {f.figure_id: f for f in golden.figures}
    qs = {q.question_id: q for q in golden.questions}
    changed = 0
    with open(sheet, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            status = (row.get("status") or "").strip().lower()
            if not status:
                continue
            new = ReviewStatus(status)
            item = figs.get(row["id"]) or qs.get(row["id"])
            if item is None:
                continue
            item.review = new
            note = (row.get("comment") or "").strip()
            if row["id"] in figs and new is ReviewStatus.CORRECTED and row.get("corrected_value"):
                value = parse_number(row["corrected_value"])
                if value is None:
                    raise SystemExit(f"{row['id']}: corrected_value {row['corrected_value']!r} is not a number")
                item.value_text = row["corrected_value"].strip()
                item.value = value
            if note and row["id"] in figs:
                item.review_note = f"reviewer: {note}. " + item.review_note
            changed += 1
    save_golden(golden)
    print(f"applied {changed} review decisions")


if __name__ == "__main__":
    if sys.argv[1] == "export":
        export_sheet()
    elif sys.argv[1] == "import":
        import_sheet(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
