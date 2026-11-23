"""Read a digital page from its own text layer: words, lines, blocks, headings.

The text layer is exact for every printed character, which is why numbers are
always taken from here when it exists, including inside tables that Docling
lays out. Reading order is column-aware so two-column pages do not interleave.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from src.document.model import BBox, Block, BlockType

LINE_TOLERANCE = 3.0  # points: words whose tops differ by less share a line
FRAGMENT_GAP = 1.5  # points: "3" + "9,480,469" drawn as two runs are one number
_FRAGMENT = re.compile(r"^[\d,.()%\-]+$")
_NUMBER = re.compile(r"^\(?-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?%?$|^\(?-?\d+(?:\.\d+)?\)?%?$")
_DOUBLED = re.compile(r"(\w)\1(\w)\2(\w)\3")  # "NNuummbbeerr": text drawn twice
_ETHIOPIC = re.compile(r"[ሀ-፿]")
_LATIN = re.compile(r"[A-Za-z]")
_LIST_START = re.compile(r"^(?:[-•▪●–*]|\(?[0-9ivxIVX]{1,3}[.)]|[a-z][.)])\s")


@dataclass
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    size: float = 0.0
    bold: bool = False

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def bbox(self) -> BBox:
        return BBox(x0=self.x0, top=self.top, x1=self.x1, bottom=self.bottom)


@dataclass
class Line:
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def size(self) -> float:
        sizes = [w.size for w in self.words if w.size]
        return statistics.median(sizes) if sizes else 0.0

    @property
    def bold(self) -> bool:
        return sum(w.bold for w in self.words) >= max(1, len(self.words) * 0.6)

    @property
    def bbox(self) -> BBox:
        return BBox(x0=self.x0, top=self.top, x1=self.x1, bottom=self.bottom)


@dataclass
class TextLayerPage:
    words: list[Word]
    lines: list[Line]
    char_count: int
    body_size: float
    checks: dict


def read_words(page) -> list[Word]:
    """Words from a pdfplumber page, with font size and boldness."""
    raw = page.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=["size", "fontname"])
    words = [
        Word(
            text=w["text"],
            x0=float(w["x0"]),
            top=float(w["top"]),
            x1=float(w["x1"]),
            bottom=float(w["bottom"]),
            size=round(float(w.get("size") or 0.0), 1),
            bold="bold" in str(w.get("fontname", "")).lower(),
        )
        for w in raw
        if w["text"].strip()
    ]
    return words


def _y_lines(words: list[Word]) -> list[list[Word]]:
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (round(w.top), w.x0)):
        if lines and abs(lines[-1][0].top - w.top) <= LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
    out = []
    for ln in lines:
        ln.sort(key=lambda w: w.x0)
        out.append(_merge_fragments(ln))
    return out


def _merge_fragments(words: list[Word]) -> list[Word]:
    out: list[Word] = []
    for w in words:
        prev = out[-1] if out else None
        if prev and _FRAGMENT.match(prev.text) and _FRAGMENT.match(w.text) and 0 <= w.x0 - prev.x1 < FRAGMENT_GAP:
            out[-1] = Word(prev.text + w.text, prev.x0, min(prev.top, w.top), w.x1, max(prev.bottom, w.bottom), prev.size, prev.bold)
        else:
            out.append(w)
    return out


def _segments(line: list[Word], gap: float) -> list[Line]:
    """Split one visual line where a horizontal gap separates columns."""
    segs: list[Line] = [Line([line[0]])]
    for w in line[1:]:
        if w.x0 - segs[-1].words[-1].x1 > gap and not (_NUMBER.match(w.text) or _NUMBER.match(segs[-1].words[-1].text)):
            segs.append(Line([w]))
        else:
            segs[-1].words.append(w)
    return segs


def _gutter(segments: list[Line], page_width: float) -> float | None:
    """x position of a two-column gutter, if most lines break around it."""
    mids = []
    pairs = 0
    rows: dict[float, list[Line]] = {}
    for s in segments:
        rows.setdefault(round(s.top / LINE_TOLERANCE), []).append(s)
    for segs in rows.values():
        if len(segs) == 2:
            pairs += 1
            mids.append((segs[0].x1 + segs[1].x0) / 2)
    if pairs < max(6, len(rows) * 0.35) or not mids:
        return None
    g = statistics.median(mids)
    if not (page_width * 0.3 < g < page_width * 0.7):
        return None
    close = sum(abs(m - g) < 25 for m in mids)
    return g if close >= pairs * 0.7 else None


def _reading_order(segments: list[Line], page_width: float) -> list[Line]:
    gutter = _gutter(segments, page_width)
    if gutter is None:
        return sorted(segments, key=lambda s: (round(s.top / LINE_TOLERANCE), s.x0))
    # Full-width segments (headings, wide tables) break the page into bands;
    # within a band, read the left column, then the right.
    ordered: list[Line] = []
    band: list[Line] = []

    def flush() -> None:
        left = sorted((s for s in band if s.x1 <= gutter + 5), key=lambda s: s.top)
        right = sorted((s for s in band if s.x1 > gutter + 5), key=lambda s: s.top)
        ordered.extend(left + right)
        band.clear()

    for s in sorted(segments, key=lambda s: (s.top, s.x0)):
        spans = s.x0 < gutter - 10 and s.x1 > gutter + 10
        if spans:
            flush()
            ordered.append(s)
        else:
            band.append(s)
    flush()
    return ordered


def analyse_page(page) -> TextLayerPage:
    words = read_words(page)
    char_count = sum(len(w.text) for w in words)
    sizes = [w.size for w in words for _ in range(len(w.text)) if w.size]
    body = statistics.mode(sizes) if sizes else 0.0
    heights = [w.bottom - w.top for w in words]
    gap = max(12.0, 2.5 * (statistics.median(heights) if heights else 10.0))
    segments = [seg for ln in _y_lines(words) for seg in _segments(ln, gap)]
    lines = _reading_order(segments, float(page.width))
    text = " ".join(w.text for w in words)
    checks = {
        "chars": char_count,
        "cid_glyphs": text.count("(cid:"),
        "replacement_chars": text.count("�"),
        "doubled_runs": len(_DOUBLED.findall(text)),
        "ethiopic_ratio": round(len(_ETHIOPIC.findall(text)) / max(1, len(_ETHIOPIC.findall(text)) + len(_LATIN.findall(text))), 3),
    }
    return TextLayerPage(words=words, lines=lines, char_count=char_count, body_size=body, checks=checks)


def garbled_ratio(tl: TextLayerPage) -> float:
    """Share of characters that are clearly broken (cid glyphs, replacement chars, doubled runs)."""
    bad = tl.checks["cid_glyphs"] * 6 + tl.checks["replacement_chars"] + tl.checks["doubled_runs"] * 12
    return min(1.0, bad / max(1, tl.char_count))


def script_of(tl: TextLayerPage) -> str:
    r = tl.checks["ethiopic_ratio"]
    if tl.char_count == 0:
        return "none"
    if r > 0.6:
        return "ethiopic"
    if r > 0.1:
        return "mixed"
    return "latin"


def blocks_from_lines(
    lines: list[Line],
    page_no: int,
    body_size: float,
    heading_levels: dict[float, int] | None = None,
) -> list[Block]:
    """Group ordered lines into paragraphs, headings and list items."""
    blocks: list[Block] = []
    buf: list[Line] = []

    def heading_level(line: Line) -> int | None:
        if len(line.words) > 14 or line.text.rstrip().endswith((".", ",", ";")):
            return None
        if body_size and line.size >= body_size * 1.15:
            if heading_levels and line.size in heading_levels:
                return heading_levels[line.size]
            return 2
        if line.bold and len(line.words) <= 10 and not _NUMBER.match(line.words[-1].text):
            return (max(heading_levels.values()) + 1) if heading_levels else 3
        return None

    def flush() -> None:
        if not buf:
            return
        text = " ".join(ln.text for ln in buf)
        bbox = buf[0].bbox
        for ln in buf[1:]:
            bbox = bbox.union(ln.bbox)
        btype = BlockType.LIST_ITEM if _LIST_START.match(text) else BlockType.TEXT
        blocks.append(Block(block_id=f"p{page_no}-b{len(blocks)}", type=btype, text=text, bbox=bbox))
        buf.clear()

    prev: Line | None = None
    for ln in lines:
        level = heading_level(ln)
        if level is not None:
            flush()
            blocks.append(Block(block_id=f"p{page_no}-b{len(blocks)}", type=BlockType.HEADING, text=ln.text, bbox=ln.bbox, level=level))
            prev = None
            continue
        if prev is not None:
            gap = ln.top - prev.bottom
            new_para = (
                gap > max(4.0, (prev.bottom - prev.top) * 0.9)
                or abs(ln.x0 - prev.x0) > 40
                or _LIST_START.match(ln.text)
                or gap < -2  # jumped to another column
            )
            if new_para:
                flush()
        buf.append(ln)
        prev = ln
    flush()
    return blocks


def text_in_box(words: list[Word], box: BBox, slack: float = 1.5) -> str | None:
    """Text-layer words whose centre lies in ``box``, in reading order."""
    inside = [w for w in words if box.contains_point(w.cx, w.cy, slack)]
    if not inside:
        return None
    lines = _y_lines(inside)
    return " ".join(" ".join(w.text for w in ln) for ln in lines)


def looks_like_table_page(tl: TextLayerPage) -> bool:
    """A page with several lines of a label followed by two or more numbers."""
    rows = 0
    for ln in _y_lines(tl.words):
        nums = [w for w in ln if _NUMBER.match(w.text)]
        if len(nums) >= 2 and any(_LATIN.search(w.text) or _ETHIOPIC.search(w.text) for w in ln):
            rows += 1
    return rows >= 4
