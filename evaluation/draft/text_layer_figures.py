"""Draft key figures from a digital PDF's own text layer.

For digital PDFs the text layer is ground truth for every printed number, so
figures drawn from it are exact. What needs a person's check is the meaning:
the row label, the column (period) the number belongs to, and the table's
scale ("in ETB million"). Each draft therefore carries the source line and a
box, and starts as ``review = draft``.

Method: words are grouped into lines by their vertical position. A line with a
text label followed by two or more numbers is a table row. Each number is
assigned to the column header above it whose horizontal centre is closest
(within ``MAX_COLUMN_GAP`` points). Header cells must look like periods
(years, fiscal years, quarters) so every figure has an unambiguous period.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from evaluation.numbers import parse_number

LINE_TOLERANCE = 3.0  # points: words whose tops differ by less share a line
MAX_COLUMN_GAP = 45.0  # points between a number's centre and its header's centre
HEADER_SEARCH_HEIGHT = 260.0  # how far above a row to look for its header line

_NUM_TOKEN = re.compile(r"^\(?-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?%?$|^\(?-?\d+(?:\.\d+)?\)?%?$")
_PERIOD_TOKEN = re.compile(
    r"^(?:FY)?(?:19|20)\d{2}(?:[/-](?:\d{2}|\d{4}))?$|^Q[1-4]$|^(?:19|20)\d{2}/\d{2}$",
    re.IGNORECASE,
)
_YEAR = re.compile(r"^\(?(?:19|20)\d{2}\)?$")
_SCALE_PATTERNS = [
    (re.compile(r"in\s+(?:ETB|birr|USD|US\$)?\s*millions?|(?:ETB|birr|USD)\s*(?:in\s*)?millions?|\bmn\b", re.I), 1e6),
    (re.compile(r"in\s+(?:ETB|birr|USD)?\s*billions?|(?:ETB|birr|USD)\s*billions?", re.I), 1e9),
    (re.compile(r"in\s+(?:ETB|birr|USD)?\s*thousands?|['’]000|\b000s\b", re.I), 1e3),
]
_CURRENCY = re.compile(r"\b(ETB|Birr|USD|US\$)\b", re.I)

# Row labels that recur in many tables and mean nothing without their table.
_GENERIC_LABEL = re.compile(
    r"^(total|sub-?total|net\b|balance|as at|as of|at \d|additions?|disposals?|less\b|add\b|actual|"
    r"budget|opening|closing|charge for|transfers?|reclassification|adjustments?|other|others|"
    r"see note|note\b|current|non-current|amount|value|percent|share)",
    re.IGNORECASE,
)
# Header words that are not column names.
_WEAK_HEADERS = {
    "for", "the", "and", "of", "in", "currency", "birr", "etb", "usd", "compared", "inflation",
    "average", "obs", "liability", "april", "june", "july", "note", "notes", "amount", "rate",
}


@dataclass
class _Line:
    top: float
    bottom: float
    words: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w["text"] for w in self.words)


@dataclass
class DraftFigure:
    page: int
    row_label: str
    column_label: str
    value_text: str
    value: float
    scale: float
    scale_note: str
    unit: str
    bbox: list[float]
    table_title: str
    source_line: str
    header_kind: str = "period"


def _group_lines(words: list[dict]) -> list[_Line]:
    lines: list[_Line] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1].top - w["top"]) <= LINE_TOLERANCE:
            lines[-1].words.append(w)
            lines[-1].bottom = max(lines[-1].bottom, w["bottom"])
        else:
            lines.append(_Line(top=w["top"], bottom=w["bottom"], words=[w]))
    for line in lines:
        line.words.sort(key=lambda w: w["x0"])
        line.words = _merge_number_fragments(line.words)
    return lines


_FRAGMENT = re.compile(r"^[\d,.()%\-]+$")
FRAGMENT_GAP = 1.5  # points; some PDFs draw "39,480,469" as "3" + "9,480,469"


def _merge_number_fragments(words: list[dict]) -> list[dict]:
    out: list[dict] = []
    for w in words:
        prev = out[-1] if out else None
        if (
            prev is not None
            and _FRAGMENT.match(prev["text"])
            and _FRAGMENT.match(w["text"])
            and 0 <= w["x0"] - prev["x1"] < FRAGMENT_GAP
        ):
            out[-1] = {
                **prev,
                "text": prev["text"] + w["text"],
                "x1": w["x1"],
                "bottom": max(prev["bottom"], w["bottom"]),
            }
        else:
            out.append(dict(w))
    return out


def _centre(w: dict) -> float:
    return (w["x0"] + w["x1"]) / 2


def _page_scale(text: str) -> tuple[float, str]:
    for pattern, scale in _SCALE_PATTERNS:
        m = pattern.search(text)
        if m:
            return scale, f"page says '{m.group(0).strip()}'"
    return 1.0, "no scale stated on the page"


def _header_for(line: _Line, lines: list[_Line], nums: list[dict]) -> tuple[list[dict], str]:
    """Column header cells above ``line``: period words if any, else any words
    sitting over at least two of the row's numbers. Returns (cells, kind)."""
    above = [ln for ln in lines if ln.bottom <= line.top and line.top - ln.bottom <= HEADER_SEARCH_HEIGHT]
    for cand in reversed(above):
        periods = [w for w in cand.words if _PERIOD_TOKEN.match(w["text"].strip("()"))]
        if len(periods) >= 2:
            return periods, "period"
    for cand in reversed(above[-6:]):
        if any(_NUM_TOKEN.match(w["text"]) for w in cand.words):
            continue  # another data row, not a header
        aligned = [
            w for w in cand.words
            if re.search(r"[A-Za-z]{2,}", w["text"])
            and min(abs(_centre(w) - _centre(n)) for n in nums) <= MAX_COLUMN_GAP / 2
        ]
        if len(aligned) >= 2:
            return aligned, "category"
    return [], ""


def _garbled(label: str) -> bool:
    toks = label.split()
    singles = sum(1 for t in toks if len(t) == 1)
    return len(toks) >= 4 and singles / len(toks) > 0.3


def _table_title(line: _Line, lines: list[_Line]) -> str:
    for cand in reversed([ln for ln in lines if ln.bottom <= line.top and line.top - ln.bottom <= 400]):
        if re.match(r"^(Table|TABLE|Schedule|Note)\s", cand.text):
            return cand.text[:160]
    return ""


def draft_page(page, page_no: int) -> list[DraftFigure]:
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    if not words:
        return []
    lines = _group_lines(words)
    page_text = "\n".join(ln.text for ln in lines)
    scale, scale_note = _page_scale(page_text)
    currency = _CURRENCY.search(page_text)
    out: list[DraftFigure] = []
    for line in lines:
        nums = [w for w in line.words if _NUM_TOKEN.match(w["text"]) and not _YEAR.match(w["text"])]
        if len(nums) < 2:
            continue
        first_num_x = min(w["x0"] for w in nums)
        # A table row has its label on the left and only numbers to the right
        # of the first number. Prose with numbers in it fails this test.
        right = [w for w in line.words if w["x0"] >= first_num_x]
        if any(not (_NUM_TOKEN.match(w["text"]) or w["text"] in {"-", "–", "—", "%"}) for w in right):
            continue
        label_words = [w for w in line.words if w["x1"] <= first_num_x and not _NUM_TOKEN.match(w["text"])]
        label = " ".join(w["text"] for w in label_words).strip(" .:-")
        alpha = re.findall(r"[A-Za-zሀ-፿]{2,}", label)
        if len(alpha) < 1 or len(label) < 5 or len(label) > 80:
            continue
        if _PERIOD_TOKEN.match(label.split()[0].strip("()")):
            continue  # transposed table (periods as rows); its columns are not periods
        if _garbled(label):
            continue  # overlapping characters in the text layer, e.g. "A T M I n te r"
        header, header_kind = _header_for(line, lines, nums)
        if not header:
            continue
        for w in nums:
            col = min(header, key=lambda h: abs(_centre(h) - _centre(w)))
            if abs(_centre(col) - _centre(w)) > MAX_COLUMN_GAP:
                continue
            value = parse_number(w["text"])
            if value is None or abs(value) < 10 and "." not in w["text"]:
                continue  # tiny integers are usually note numbers
            is_pct = w["text"].endswith("%")
            out.append(
                DraftFigure(
                    page=page_no,
                    row_label=label,
                    column_label=col["text"].strip("()"),
                    value_text=w["text"],
                    value=value,
                    scale=1.0 if is_pct else scale,
                    scale_note="percentage" if is_pct else scale_note,
                    unit="%" if is_pct else (currency.group(1).upper().replace("BIRR", "ETB") if currency else ""),
                    bbox=[round(w["x0"], 1), round(w["top"], 1), round(w["x1"], 1), round(w["bottom"], 1)],
                    table_title=_table_title(line, lines),
                    source_line=line.text[:200],
                    header_kind=header_kind,
                )
            )
    return out


def draft_document(pdf_path: Path) -> list[DraftFigure]:
    drafts: list[DraftFigure] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            try:
                drafts.extend(draft_page(page, i))
            except Exception:  # a malformed page should not stop drafting
                continue
            page.flush_cache()
    return drafts


def select(drafts: list[DraftFigure], k: int, seed: int) -> list[DraftFigure]:
    """Pick ``k`` figures with unambiguous labels, spread across pages."""
    # A label is usable when it names one row in the document, or one row
    # within a titled table (the question then names the table).
    def key(d: DraftFigure) -> str:
        return d.row_label.lower()

    label_rows: dict[str, set[tuple[int, float]]] = {}
    titled_rows: dict[tuple[str, str], set[tuple[int, float]]] = {}
    for d in drafts:
        label_rows.setdefault(key(d), set()).add((d.page, round(d.bbox[1])))
        if d.table_title:
            titled_rows.setdefault((key(d), d.table_title), set()).add((d.page, round(d.bbox[1])))
    unique = [
        d for d in drafts
        if len(label_rows[key(d)]) == 1
        or (d.table_title and len(titled_rows[(key(d), d.table_title)]) == 1)
    ]
    unique = [d for d in unique if not _GENERIC_LABEL.match(d.row_label)]
    # Period columns give unambiguous questions; category columns are used only
    # when their header is a real word and the document has too few periods.
    periods = [d for d in unique if d.header_kind == "period"]
    if len(periods) >= max(6, k // 2):
        unique = periods
    else:
        unique = periods + [
            d for d in unique
            if d.header_kind == "category" and d.column_label.lower().strip(":") not in _WEAK_HEADERS
            and len(d.column_label.strip(":")) >= 4
        ]
    rng = random.Random(seed)
    by_page: dict[int, list[DraftFigure]] = {}
    for d in unique:
        by_page.setdefault(d.page, []).append(d)
    pages = sorted(by_page)
    rng.shuffle(pages)
    chosen: list[DraftFigure] = []
    while len(chosen) < k and pages:
        for p in list(pages):
            pool = [d for d in by_page[p] if d not in chosen]
            if not pool:
                pages.remove(p)
                continue
            chosen.append(rng.choice(pool))
            if len(chosen) >= k:
                break
    return sorted(chosen, key=lambda d: (d.page, d.bbox[1], d.bbox[0]))
