"""Extract a schema's fields from a document, page by page, grounded to boxes.

1. Pick pages: score every page by the schema's page titles and each field's
   `find` words; read the best few (all pages of a short document).
2. Read each page with one model call (in parallel). The page is shown as
   blocks and table cells with ids (``p12-b3``, ``p12-t0-r5-c2``); the model
   copies each field it finds exactly as printed and cites the id.
3. Ground: the cited block or cell must print the value. A wrong id is
   re-pointed to the cell that does print it; a value printed nowhere on the
   page is "ungrounded". The id gives the page and box.
4. Merge the pages: per field, the best grounded candidate wins (statement
   pages over highlights); candidates that disagree send it to review.
5. Validate: types, the schema's rules (assets = liabilities + equity,
   subtotal + VAT = total, ...). A field below the confidence threshold,
   ungrounded, or in a broken rule goes to the review queue.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from src.agents.json_util import extract_json
from src.document.model import BBox, BlockType, DocumentModel, Page
from src.llm import usage
from src.llm.base import LLMClient
from src.llm.errors import LLMError
from src.schemas import values as V
from src.schemas.schema import FieldSpec, Schema

logger = logging.getLogger("docmind.schemas")

_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="docmind-fields")
PAGE_CHARS = 14000


def review_threshold() -> float:
    try:
        return float(os.getenv("DOCMIND_FIELD_REVIEW_THRESHOLD", "0.75"))
    except ValueError:
        return 0.75


# --- results ------------------------------------------------------------------------


@dataclass
class FieldValue:
    name: str
    value: Any = None  # str | float | "YYYY-MM-DD" | list[dict] (line items)
    printed: str | None = None
    unit: str | None = None  # money: the scale/currency text as printed ("Birr'000")
    page: int | None = None
    ref: str | None = None  # block or cell id
    bbox: list[float] | None = None  # [x0, top, x1, bottom], points, top-left origin
    confidence: float = 0.0
    grounded: bool = False
    status: str = "missing"  # auto | needs_review | missing
    reasons: list[str] = field(default_factory=list)
    alternatives: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionResult:
    schema: str
    schema_version: int
    document_id: str
    fields: dict[str, FieldValue]
    rules: list[dict] = field(default_factory=list)
    pages_read: list[int] = field(default_factory=list)
    seconds: float = 0.0
    usage: dict = field(default_factory=dict)
    model: str = ""

    @property
    def needs_review(self) -> list[str]:
        return [n for n, f in self.fields.items() if f.status == "needs_review"]

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "rules": self.rules,
            "pages_read": self.pages_read,
            "seconds": round(self.seconds, 2),
            "usage": self.usage,
            "model": self.model,
            "needs_review": self.needs_review,
        }


# --- the page as the model sees it -------------------------------------------------------


@dataclass
class Ref:
    text: str
    bbox: BBox | None
    confidence: float | None = None


def serialize_page(page: Page, *, limit: int = PAGE_CHARS) -> tuple[str, dict[str, Ref]]:
    """Blocks and table cells with ids, in reading order."""
    refs: dict[str, Ref] = {}
    lines: list[str] = []
    tables = {t.table_id: t for t in page.tables}
    shown: set[str] = set()
    for b in page.blocks:
        if b.type is BlockType.TABLE and b.text in tables:
            t = tables[b.text]
            shown.add(t.table_id)
            lines.extend(_table_lines(t, refs))
        elif b.text.strip() and b.type not in (BlockType.FIGURE,):
            refs[b.block_id] = Ref(b.text, b.bbox, b.confidence)
            lines.append(f"[{b.block_id}] {b.text.strip()}")
    for t in page.tables:
        if t.table_id not in shown:
            lines.extend(_table_lines(t, refs))
    text = "\n".join(lines)
    return text[:limit], refs


def _table_lines(t, refs: dict[str, Ref]) -> list[str]:
    rows: dict[int, list] = {}
    for c in t.cells:
        rows.setdefault(c.row, []).append(c)
    out = [f"[table {t.table_id}]" + (f" {t.caption}" if t.caption else "")]
    for r in sorted(rows):
        parts = []
        for c in sorted(rows[r], key=lambda c: c.col):
            if not c.text.strip():
                continue
            rid = f"{t.table_id}-r{r}-c{c.col}"
            refs[rid] = Ref(c.text, c.bbox, None)
            parts.append(f"{rid}: {c.text.strip()}")
        if parts:
            out.append(" | ".join(parts))
    return out


# --- choosing pages ----------------------------------------------------------------------


def page_text(page: Page) -> str:
    parts = [b.text for b in page.blocks if b.type is not BlockType.TABLE]
    for t in page.tables:
        parts.extend(c.text for c in t.cells)
    return "\n".join(parts)


def page_title(page: Page) -> str:
    """The text printed in the top third of the page (where a statement's title is)."""
    limit = page.height * 0.35 if page.height else None
    parts = []
    for b in page.blocks:
        if b.type in (BlockType.TABLE, BlockType.FIGURE):
            continue
        if limit is None or b.bbox is None or b.bbox.top <= limit:
            parts.append(b.text)
    for t in page.tables:
        if t.caption:
            parts.append(t.caption)
        parts.extend(c.text for c in t.cells if c.row == 0)
    return " ".join(parts).lower()


def _row_labels(page: Page) -> str:
    """Row labels (first table column) and line starts: where "Total assets" sits on a statement."""
    labels = [c.text for t in page.tables for c in t.cells if c.col == 0]
    labels += [b.text.split("\n")[0][:80] for b in page.blocks if b.type is BlockType.TEXT]
    return "\n".join(labels).lower()


def _has_words(phrase: str, lines: list[set[str]]) -> bool:
    """All words of ``phrase`` on one line, in any order: "Profit / (Loss) before tax" has "profit before tax"."""
    words = set(V.norm_text(phrase).split())
    return bool(words) and any(words <= line for line in lines)


def page_kinds(page: Page, schema: Schema) -> dict[str, float]:
    """How strongly a page is each of the schema's page kinds (0 = not at all)."""
    title = page_title(page)
    labels = [set(V.norm_text(x).split()) for x in _row_labels(page).splitlines()]
    full = [set(V.norm_text(x).split()) for x in page_text(page).splitlines()]
    out: dict[str, float] = {}
    for kind, titles in schema.pages.items():
        finds = {w for spec in schema.fields.values() if spec.printed_on == kind for w in spec.find}
        in_rows = {w for w in finds if _has_words(w, labels)}
        rows = len(in_rows) + 0.5 * sum(1 for w in finds - in_rows if _has_words(w, full))
        # a scan may split or garble a title ("of Financial Position" / "Statement A$ AT ..."):
        # all its words anywhere in the top of the page is enough
        title_words = set(V.norm_text(title).split())
        titled = any(t in title or set(V.norm_text(t).split()) <= title_words for t in titles)
        score = (4.0 if titled else 0.0) + rows
        if titled and rows == 0:  # a contents page lists every title, with no figures
            score = 0.5
        out[kind] = score
    return out


def choose_pages(model: DocumentModel, schema: Schema, *, max_pages: int = 6, per_kind: int = 3) -> list[int]:
    """The best pages of each kind the schema's fields are printed on, plus the first page."""
    if model.page_count <= max_pages:
        return [p.number for p in model.pages]
    chosen: list[int] = [model.pages[0].number]  # names and dates are usually on the first page
    kinds = {k for k in schema.pages if any(f.printed_on == k for f in schema.fields.values())} or set(schema.pages)
    scored = {p.number: page_kinds(p, schema) for p in model.pages}
    for kind in sorted(kinds, key=lambda k: list(schema.pages).index(k)):
        best = sorted((n for n in scored if scored[n][kind] >= 2.0), key=lambda n: (-scored[n][kind], n))
        for n in best[:per_kind]:
            if n not in chosen:
                chosen.append(n)
    if len(chosen) < max_pages:  # fill with the pages that carry the most field words
        rest = sorted(scored, key=lambda n: (-sum(scored[n].values()), n))
        for n in rest:
            if len(chosen) >= max_pages:
                break
            if n not in chosen and sum(scored[n].values()) > 0:
                chosen.append(n)
    return sorted(chosen[: max_pages + len(kinds)])


# --- one model call per page -------------------------------------------------------------

_SYSTEM = """You read ONE page of a document and copy the fields of a schema that the page prints.
The page is given as lines "<id>: <text>" for table cells and "[<id>] <text>" for text blocks.
Return ONLY JSON:
{"fields": {"<field name>": {"value": "<exactly as printed>", "ref": "<id of the block or cell>",
                             "unit": "<money only: currency and scale as printed for that column, e.g. Birr'000, ETB, in millions of Birr>",
                             "confidence": <0.0-1.0>}},
 "items": [{"description": "...", "quantity": "...", "unit_price": "...", "amount": "...", "ref": "<id of the row's first cell or block>"}]}
Rules:
- Copy values exactly as printed (keep parentheses for negatives, thousands separators, the date as printed).
  Never compute, convert or guess. Leave out every field the page does not print.
- "ref" must be the id of the cell or block that prints the value.
- confidence: 0.9+ when the label and value are unambiguous, lower when you had to choose between
  similar lines or the text looks garbled.
{guidance}"""


def _field_list(schema: Schema) -> str:
    lines = []
    for spec in schema.fields.values():
        if spec.type == "list":
            cols = ", ".join(spec.item)
            lines.append(f"- {spec.name} (one entry per line in \"items\", columns: {cols}): {spec.description}")
        else:
            lines.append(f"- {spec.name} ({spec.type}): {spec.description}")
    return "\n".join(lines)


def _guidance(schema: Schema) -> str:
    g = f"- {schema.description.strip()}" if schema.description else ""
    if schema.name == "financial_statement_summary":
        g += (
            "\n- Use the current-year column, never the comparative (prior-year) column. When a statement has Group"
            " (consolidated) and Bank / Company (separate) columns, use the Bank / Company column."
            "\n- Prefer the primary statements (statement of financial position, profit or loss) over highlights."
        )
    return g


def read_page(llm: LLMClient, schema: Schema, page: Page) -> tuple[dict, dict[str, Ref]]:
    text, refs = serialize_page(page)
    if not text.strip():
        return {}, refs
    system = _SYSTEM.replace("{guidance}", _guidance(schema))
    prompt = f"schema: {schema.label or schema.name}\nfields:\n{_field_list(schema)}\n\npage {page.number}:\n{text}\n\nReturn the JSON now."
    with usage.purpose("fields"):
        res = llm.complete(prompt, system=system, response_format="json", temperature=0.0, max_tokens=6000)
    data = extract_json(res.text)
    if not isinstance(data, dict) or not data:
        logger.warning("page %s: the model's reply was not usable JSON (%d chars)", page.number, len(res.text or ""))
        return {}, refs
    return data, refs


# --- grounding ---------------------------------------------------------------------------


def _holds(spec_type: str, text: str, printed: str | None, normalized: Any) -> bool:
    if printed is None:
        return False
    if spec_type in ("money", "number"):
        return V.text_holds_amount(text, printed)
    if spec_type == "date":
        return V.text_holds_date(text, normalized if isinstance(normalized, date) else V.parse_date(printed)) or V.norm_text(printed) in V.norm_text(text)
    if spec_type == "code":
        return bool(V.norm_text(printed)) and (V.norm_text(printed) in V.norm_text(text) or V.currency_code(text) == V.currency_code(printed))
    return V.same_text(printed, text, threshold=0.6) or V.norm_text(printed) in V.norm_text(text)


_CELL_REF = re.compile(r"^(p\d+-t\d+)-r(\d+)-c(\d+)$")


def total_column(page: Page, ref: str) -> tuple[str, str] | None:
    """For a cell in a business-line column, the same row's Total cell (ref, text), when the parts add up.

    Insurers print "General | Long-term | Total | Total (last year)": the model
    tends to take the first number. A cell whose header says "total", equal to
    the picked cell plus another cell of the row, is the company's figure.
    """
    m = _CELL_REF.match(ref)
    if not m:
        return None
    table = next((t for t in page.tables if t.table_id == m.group(1)), None)
    if table is None:
        return None
    row, col = int(m.group(2)), int(m.group(3))
    header: dict[int, str] = {}
    for c in table.cells:
        if c.row <= 1 and (c.is_header or c.row == 0 or not V.parse_amount(c.text)):
            header[c.col] = (header.get(c.col, "") + " " + c.text).lower()
    if "total" in header.get(col, ""):
        return None
    cells = {c.col: c for c in table.cells if c.row == row}
    values = {k: V.parse_amount(c.text) for k, c in cells.items()}
    picked = values.get(col)
    if picked is None:
        return None
    for j in sorted(k for k in cells if k != col and "total" in header.get(k, "")):
        total = values.get(j)
        if total is None:
            continue
        for k, other in values.items():
            if k in (col, j) or other is None:
                continue
            if V.same_amount(abs(picked) + abs(other), abs(total), rel=0.001, abs_tol=1.5):
                return f"{table.table_id}-r{row}-c{j}", cells[j].text
    return None


def clean_ref(ref: Any) -> str | None:
    """``"[p1-b28]"`` -> ``"p1-b28"``."""
    if not ref:
        return None
    return str(ref).strip().strip("[]() ").split()[0] or None


def ground(spec_type: str, printed: str | None, ref: str | None, refs: dict[str, Ref], normalized: Any = None) -> tuple[str | None, bool, list[str]]:
    """(ref that prints the value, grounded?, reasons)."""
    ref = clean_ref(ref)
    if ref and ref in refs and _holds(spec_type, refs[ref].text, printed, normalized):
        return ref, True, []
    for rid, r in refs.items():  # the model cited the wrong id: find the cell that prints it
        if _holds(spec_type, r.text, printed, normalized):
            return rid, True, ([f"cited {ref}, printed in {rid}"] if ref else [])
    return ref if ref in refs else None, False, ["the value is not printed on the page"]


# --- normalising ---------------------------------------------------------------------------


def normalize(spec: FieldSpec | Any, printed: Any, unit: str | None, page_text_: str = "") -> tuple[Any, list[str]]:
    """The stored value of a field (money: absolute amount, scale applied)."""
    t = spec.type
    if printed is None or str(printed).strip() == "":
        return None, []
    s = str(printed).strip()
    if t in ("money", "number"):
        v = V.parse_amount(s)
        if v is None:
            return None, [f"'{s}' is not a number"]
        if t == "money":
            scale = V.scale_of(unit) if unit else 1.0
            page_scales = [V.scale_of(m) for m in _unit_lines(page_text_)] if page_text_ else []
            page_scales = [s for s in page_scales if s != 1.0]
            if scale == 1.0 and page_scales:
                # the model often writes the currency ("Birr") and leaves out the
                # column's scale ("Birr'000"), which the page prints in the header
                scale = page_scales[0]
            elif scale != 1.0 and page_scales and scale not in page_scales:
                scale = page_scales[0]  # a scale the page never prints ("Birr'000" on an "In Bn. of Birr" page)
            return round(v * scale, 2), []
        return v, []
    if t == "date":
        d = V.parse_date(s)
        return (d.isoformat() if d else None), ([] if d else [f"'{s}' is not a date"])
    if t == "code":
        code = V.currency_code(s)
        return code or s.upper()[:8], ([] if code else [f"unknown currency '{s}'"])
    return re.sub(r"\s+", " ", s), []


_UNIT_MARK = re.compile(
    r"(?i)(?:birr|etb|br)\s*['’`]\s*[0o]{3}|in\s+(?:millions?|thousands?|billions?)\s+of\s+\w+|\(in\s+[^)]{1,30}\)"
    r"|in\s+(?:mn|bn)\.?\s+(?:of\s+)?birr|(?:birr|etb)\s+in\s+(?:millions?|thousands?|billions?)"
)


def _unit_lines(text: str) -> list[str]:
    """Every scale marker the page prints ("Birr'000", "(in Mn. Birr)", ...), in order."""
    return [m.group(0) for m in _UNIT_MARK.finditer(text or "")]


def _unit_line(text: str) -> str:
    found = _unit_lines(text)
    return found[0] if found else ""


# --- the whole document ------------------------------------------------------------------


def _page_priority(page: Page, schema: Schema, spec: FieldSpec) -> float:
    """How much a value read on ``page`` should count for ``spec``: its own statement first."""
    bonus = 0.0
    if spec.printed_on:
        kinds = page_kinds(page, schema)
        mine = kinds.get(spec.printed_on, 0.0)
        bonus += 0.4 if mine >= 4.0 else 0.2 if mine >= 2.0 else 0.0
    title = page_title(page)
    if any(t in title for t in schema.prefer_titles):
        bonus += 0.05
    if any(t in title for t in schema.avoid_titles):
        bonus -= 0.05
    return bonus


def extract_fields(
    model: DocumentModel,
    schema: Schema,
    llm: LLMClient,
    *,
    document_id: str = "",
    max_pages: int = 6,
    page_image: Callable[[int], bytes | None] | None = None,
    vision_llm: LLMClient | None = None,
) -> ExtractionResult:
    """Read ``schema``'s fields from ``model``.

    ``page_image(n)`` (a PNG of page n) lets the extractor read flagged values on
    scanned pages again from the image, with ``vision_llm`` (default: ``llm`` when
    it can see images).
    """
    started = time.perf_counter()
    pages_read = choose_pages(model, schema, max_pages=max_pages)
    by_number = {p.number: p for p in model.pages}
    with usage.collect() as events:
        futures = [(n, _POOL.submit(usage.run_in_context(read_page, llm, schema, by_number[n]))) for n in pages_read]
        page_out = []
        for n, f in futures:
            try:
                data, refs = f.result()
            except LLMError:
                raise
            except Exception as exc:  # one unreadable page must not lose the others
                logger.warning("field extraction failed on page %s: %s", n, exc)
                data, refs = {}, {}
            page_out.append((n, data, refs))

    candidates: dict[str, list[FieldValue]] = {name: [] for name in schema.fields}
    items: list[dict] = []
    # the pages read that are clearly each statement ("balance_sheet": [12, 112], ...)
    kind_pages: dict[str, list[int]] = {}
    for n in pages_read:
        for kind, score in page_kinds(by_number[n], schema).items():
            if score >= 4.0:
                kind_pages.setdefault(kind, []).append(n)
    for n, data, refs in page_out:
        ptxt = page_text(by_number[n])
        for name, raw in (data.get("fields") or {}).items():
            spec = schema.fields.get(name)
            if spec is None or spec.type == "list" or not isinstance(raw, dict):
                continue
            printed = raw.get("value")
            if printed in (None, "", "null"):
                continue
            unit = raw.get("unit")
            parsed = V.parse_date(str(printed)) if spec.type == "date" else None
            ref, grounded, reasons = ground(spec.type, str(printed), raw.get("ref"), refs, parsed)
            if spec.type == "money" and grounded and ref:
                total = total_column(by_number[n], ref)
                if total:
                    ref, printed = total
                    reasons.append("moved to the row's Total column (the parts beside it add up to it)")
            value, problems = normalize(spec, printed, unit, ptxt)
            try:
                conf = float(raw.get("confidence", 0.8))
            except (TypeError, ValueError):
                conf = 0.8
            conf = max(0.0, min(1.0, conf))
            if not grounded:
                conf *= 0.4
            if problems:
                conf *= 0.5
            if ref and refs.get(ref) and refs[ref].confidence is not None and refs[ref].confidence < 0.8:
                conf *= 0.9
                reasons.append("OCR was unsure of this text")
            own = kind_pages.get(spec.printed_on or "", [])
            if spec.printed_on and own and n not in own:
                # e.g. a profit figure read off the balance sheet, where a scan shifted the labels
                conf *= 0.7
                reasons.append(f"read on page {n}, not on the {spec.printed_on.replace('_', ' ')} (page {', '.join(map(str, own))})")
            fv = FieldValue(
                name=name, value=value, printed=str(printed), unit=unit, page=n, ref=ref, status="found",
                bbox=refs[ref].bbox.as_list() if ref and refs.get(ref) and refs[ref].bbox else None,
                confidence=round(conf, 3), grounded=grounded, reasons=reasons + problems,
            )
            fv._priority = conf + _page_priority(by_number[n], schema, spec)  # type: ignore[attr-defined]
            candidates[name].append(fv)
        for raw in data.get("items") or []:
            if isinstance(raw, dict):
                items.append(_item(schema, raw, n, refs))

    fields: dict[str, FieldValue] = {}
    for name, spec in schema.fields.items():
        if spec.type == "list":
            fields[name] = _list_field(name, items)
            continue
        for c in candidates[name]:  # the same value read on several pages is more likely the one meant
            agree = sum(1 for o in candidates[name] if o is not c and o.page != c.page and _same(spec, o.value, c.value))
            bonus = 0.1 * min(agree, 3)
            if spec.type == "text" and spec.find and any(w in V.norm_text(str(c.value)).split() or w in V.norm_text(str(c.value)) for w in spec.find):
                bonus += 0.2  # it reads like the thing asked for ("... Share Company", "... Bank")
            c._priority = getattr(c, "_priority", c.confidence) + bonus  # type: ignore[attr-defined]
        cands = sorted(candidates[name], key=lambda f: -getattr(f, "_priority", f.confidence))
        if not cands:
            fields[name] = FieldValue(name=name, status="missing", reasons=["not found"] if spec.required else [])
            continue
        best = cands[0]
        if spec.type == "text":  # "CBE" is the acronym of "Commercial Bank of Ethiopia": the full name is the answer
            full = next((c for c in cands[1:] if _is_acronym(str(best.value), str(c.value)) and c.grounded), None)
            if full is not None:
                full.reasons.append(f"the full name of '{best.printed}'")
                best = full
        others = [c for c in cands if c is not best and not _same(spec, c.value, best.value)]
        if others and getattr(others[0], "_priority", 0) >= getattr(best, "_priority", 0) - 0.1:
            best.reasons.append(f"another page gives {others[0].printed} (page {others[0].page})")
            best.confidence = round(best.confidence * 0.8, 3)
        best.alternatives = [{"value": o.value, "printed": o.printed, "page": o.page} for o in others[:3]]
        fields[name] = best

    _resolve_with_rules(schema, fields, candidates, kind_pages)
    _currency_from_amounts(schema, fields)
    for name, fv in fields.items():
        spec = schema.fields[name]
        if fv.value in (None, []) or spec.type == "list":
            continue
        if spec.pattern and not re.fullmatch(spec.pattern, str(fv.value)):
            fv.reasons.append(f"does not look like a {spec.label or name}")
            fv.confidence = round(fv.confidence * 0.5, 3)
        if spec.type == "text" and _ID_FIELD.search(name) and re.search(r"[!|]", str(fv.value)):
            fv.reasons.append("has characters a scan often misreads (! or |)")
            fv.confidence = round(fv.confidence * 0.6, 3)
    rules = _set_statuses(schema, fields)

    reread: list[int] = []
    if page_image is not None:
        vision = vision_llm or (llm if _sees_images(llm) else None)
        if vision is not None:
            with usage.collect() as more:
                reread = reread_from_images(model, schema, fields, kind_pages, page_image, vision)
            events.extend(more)
            if reread:
                rules = _set_statuses(schema, fields, fresh=True)

    return ExtractionResult(
        schema=schema.name,
        schema_version=schema.version,
        document_id=document_id or model.doc_id,
        fields=fields,
        rules=rules,
        pages_read=pages_read,
        seconds=time.perf_counter() - started,
        usage=usage.summarize(events) | ({"pages_reread_from_image": reread} if reread else {}),
        model=f"{llm.provider}/{llm.model}",
    )


def _set_statuses(schema: Schema, fields: dict[str, FieldValue], *, fresh: bool = False) -> list[dict]:
    """Check the rules and give every field its status (auto / needs_review / missing)."""
    rules = check_rules(schema, fields)
    threshold = review_threshold()
    for name, fv in fields.items():
        if fresh:
            fv.reasons = [r for r in fv.reasons if not r.startswith("breaks ")]
        if fv.value in (None, []):
            fv.status = "needs_review" if schema.fields[name].required else "missing"
            continue
        broken = [r for r in rules if not r["passed"] and not r["soft"] and name in r["fields"]]
        conf = fv.confidence
        if broken:
            fv.reasons.append("breaks " + ", ".join(r["name"] for r in broken))
            conf = round(conf * 0.7, 3)
        fv.status = "auto" if (fv.grounded and conf >= threshold and not broken) else "needs_review"
    return rules


def page_images(pdf_path) -> Callable[[int], bytes | None]:
    """``n`` -> a PNG of page ``n`` of the PDF (about 150 dpi), for re-reading scanned values."""

    def render(n: int) -> bytes | None:
        import io

        import pypdfium2 as pdfium

        try:
            pdf = pdfium.PdfDocument(str(pdf_path))
            try:
                img = pdf[n - 1].render(scale=150 / 72).to_pil().convert("L")
            finally:
                pdf.close()
        except Exception as exc:  # a missing file only means no second look
            logger.warning("could not render page %s of %s: %s", n, pdf_path, exc)
            return None
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        return buf.getvalue()

    return render


def _sees_images(llm: LLMClient) -> bool:
    from src.llm import registry

    return registry.resolve(llm.model).supports_vision


# --- reading a scanned page's image again ------------------------------------------------------

_VISION_SYSTEM = """You read values from the IMAGE of one page of a document. The page's text was produced
by OCR and may be wrong: trust the image. Copy each value exactly as printed (with parentheses for
negatives and thousands separators). Never compute.
Return ONLY JSON: {"fields": {"<name>": {"value": "<as printed>", "unit": "<scale and currency of that column, e.g. Birr'000>", "confidence": <0-1>}}}
Leave out a field the image does not show.
{guidance}"""


def reread_from_images(
    model: DocumentModel,
    schema: Schema,
    fields: dict[str, FieldValue],
    kind_pages: dict[str, list[int]],
    page_image: Callable[[int], bytes | None],
    vision: LLMClient,
    *,
    max_pages: int = 2,
) -> list[int]:
    """Read flagged values on scanned pages from the page image; keep a new value only if it
    makes the schema's rules hold (or fills a field that was not found). Returns the pages read."""
    by_number = {p.number: p for p in model.pages}
    scanned = {p.number for p in model.pages if p.quality.engine in ("ocr", "vision")}
    wanted: dict[int, list[str]] = {}
    for name, f in fields.items():
        spec = schema.fields[name]
        if f.status != "needs_review" or spec.type in ("list", "code"):
            continue
        page = f.page
        if page is None:
            own = [n for n in kind_pages.get(spec.printed_on or "", []) if n in scanned]
            page = own[0] if own else None
        if page in scanned:
            wanted.setdefault(page, []).append(name)
    if not wanted:
        return []
    pages = sorted(wanted, key=lambda n: -len(wanted[n]))[:max_pages]
    before, _ = _rules_held(schema, fields)
    done = []
    for n in pages:
        image = page_image(n)
        if not image:
            continue
        names = wanted[n]
        # no OCR value in the prompt: shown one, the model copies it back
        listing = "\n".join(
            f"- {nm} ({schema.fields[nm].type}): {schema.fields[nm].description}"
            + (f" Its row is labelled like: {', '.join(schema.fields[nm].find[:4])}." if schema.fields[nm].find else "")
            for nm in names
        )
        messages = [
            {"role": "system", "content": _VISION_SYSTEM.replace("{guidance}", _guidance(schema))},
            {"role": "user", "content": [
                {"type": "text", "text": f"page {n}. Read these fields:\n{listing}\nReturn the JSON now."},
                {"type": "image", "image": image, "mime": "image/png", "detail": "high"},
            ]},
        ]
        try:
            with usage.purpose("fields"):
                res = vision.chat(messages, response_format="json", temperature=0.0, max_tokens=600)
        except LLMError:
            raise
        except Exception as exc:  # pragma: no cover - a failed second look keeps the first
            logger.warning("re-reading page %s from its image failed: %s", n, exc)
            continue
        done.append(n)
        data = extract_json(res.text)
        ptxt = page_text(by_number[n])
        trial = dict(fields)
        changed = []
        for nm, raw in ((data or {}).get("fields") or {}).items():
            if nm not in names or not isinstance(raw, dict) or raw.get("value") in (None, ""):
                continue
            spec = schema.fields[nm]
            value, problems = normalize(spec, raw["value"], raw.get("unit"), ptxt)
            if value is None or problems:
                continue
            old = fields[nm]
            trial[nm] = FieldValue(
                name=nm, value=value, printed=str(raw["value"]), unit=raw.get("unit"), page=n, ref=old.ref, bbox=old.bbox,
                confidence=0.85, grounded=True, status="found",
                reasons=["read again from the page image: the scan's text was unclear"],
                alternatives=([{"value": old.value, "printed": old.printed, "page": old.page}] if old.value is not None else []),
            )
            changed.append(nm)
        if not changed:
            continue
        for nm in list(changed):
            old = fields[nm]
            if old.value is not None and not old.grounded and _same(schema.fields[nm], old.value, trial[nm].value):
                old.grounded = True  # the image prints what the model read through the OCR noise
                old.confidence = max(old.confidence, 0.85)
                old.reasons = [r for r in old.reasons if r != "the value is not printed on the page"]
                old.reasons.append("confirmed on the page image")
                changed.remove(nm)
                trial[nm] = old
        if not changed:
            continue
        after, held = _rules_held(schema, trial)
        filled_only = all(fields[nm].value is None for nm in changed) and after >= before
        if after > before or filled_only:
            for nm in changed:
                if held or fields[nm].value is None:
                    trial[nm].reasons.append("its rules hold with it" if held else "the field was missing")
                fields[nm] = trial[nm]
            before = after
    return done


def _rules_held(schema: Schema, fields: dict[str, FieldValue]) -> tuple[int, list[str]]:
    ok = [r["name"] for r in check_rules(schema, fields) if not r["soft"] and r["passed"] and "not checked" not in r["detail"]]
    return len(ok), ok


_ID_FIELD = re.compile(r"(number|_no|_id|code)$")


def _is_acronym(short: str, long: str) -> bool:
    """``"CBE"`` and ``"Commercial Bank of Ethiopia"``; ``"Ethio RE"`` and ``"Ethiopian Reinsurance"``."""
    s = re.sub(r"[^A-Za-z]", "", short)
    words = [w for w in re.findall(r"[A-Za-z]+", long) if w.lower() not in ("of", "and", "the", "for", "s", "c", "sc")]
    if not s or len(words) < 2 or len(s) >= len(re.sub(r"[^A-Za-z]", "", long)):
        return False
    initials = "".join(w[0] for w in words).lower()
    if s.lower() == initials or s.lower() in (initials[:len(s)],):
        return True
    # a short form made of the starts of the long name's words ("Ethio RE")
    parts = re.findall(r"[A-Za-z]+", short)
    return len(parts) >= 2 and all(any(w.lower().startswith(p.lower()) for w in words) for p in parts)


def _resolve_with_rules(
    schema: Schema, fields: dict[str, FieldValue], candidates: dict[str, list[FieldValue]], kind_pages: dict[str, list[int]] | None = None
) -> None:
    """When a sum rule fails, look for the pages' values that make it hold.

    A two-page invoice prints a "Previous balance" on page 1 and the totals on
    page 2; a report prints the group's and the bank's balance sheets. The
    combination of candidates that adds up (and, for a subtotal, matches the
    lines) is the one the document means.
    """
    hard = [r for r in schema.rules if not r.soft and r.kind in ("sum", "sum_of_items", "differ", "ratio_between")]
    names = [n for n in dict.fromkeys(f for r in hard for f in r.fields()) if candidates.get(n) and schema.fields[n].type != "list"]
    if not names:
        return

    def held(combo: dict[str, FieldValue]) -> tuple[int, list[str]]:
        trial = {n: FieldValue(name=n, value=f.value, status=f.status, grounded=f.grounded) for n, f in fields.items()}
        for n, c in combo.items():
            trial[n].value, trial[n].grounded = c.value, c.grounded
        ok = []
        for r in check_rules(schema, trial):
            if r["soft"] or r["name"] not in {h.name for h in hard} or not r["passed"] or "not checked" in r["detail"]:
                continue
            if any(n in trial and n in names and not trial[n].grounded for n in r["fields"]):
                continue  # a rule that leans on a value the page does not print proves nothing
            ok.append(r["name"])
        return len(ok), ok

    now, _ = held({n: fields[n] for n in names})

    def allowed(n: str, c: FieldValue) -> bool:
        """Never trade a value read on its own statement for one read elsewhere."""
        kind = schema.fields[n].printed_on
        own = (kind_pages or {}).get(kind or "", [])
        return not (own and fields[n].page in own and c.page not in own)

    pools = [[c for c in candidates[n] if c.grounded and allowed(n, c)][:4] or [fields[n]] for n in names]
    if all(len(p) <= 1 for p in pools):
        return
    best, best_key = None, (now, -1e9)
    for combo in _product(pools):
        n_ok, rules_ok = held(dict(zip(names, combo)))
        key = (n_ok, sum(getattr(c, "_priority", c.confidence) for c in combo))
        if n_ok > now and key > best_key:
            best, best_key, best_rules = combo, key, rules_ok
    if best is None:
        return
    for n, c in zip(names, best):
        if c is not fields[n]:
            c.reasons.append(
                f"chosen over page {fields[n].page}'s {fields[n].printed}: it makes "
                + ", ".join(r.replace("_", " ") for r in best_rules) + " hold"
            )
            c.alternatives = [{"value": fields[n].value, "printed": fields[n].printed, "page": fields[n].page}]
            fields[n] = c


def _currency_from_amounts(schema: Schema, fields: dict[str, FieldValue]) -> None:
    """A currency the model left out is often printed beside the amounts ("ETB 13,300.00")."""
    for name, spec in schema.fields.items():
        if spec.type != "code" or fields[name].value is not None:
            continue
        for other, ospec in schema.fields.items():
            f = fields[other]
            if ospec.type != "money" or f.value is None:
                continue
            code = V.currency_code(f"{f.unit or ''} {f.printed or ''}")
            if code:
                fields[name] = FieldValue(
                    name=name, value=code, printed=f.printed, page=f.page, ref=f.ref, bbox=f.bbox,
                    confidence=0.85, grounded=True, status="found", reasons=[f"read from {ospec.label or other}"],
                )
                break


def _product(pools: list[list]) -> list[tuple]:
    out: list[tuple] = [()]
    for pool in pools:
        nxt = [t + (x,) for t in out for x in pool]
        out = nxt if len(nxt) <= 2048 else [t + (pool[0],) for t in out]  # keep the best of the rest
    return out


def _same(spec: FieldSpec, a: Any, b: Any) -> bool:
    if spec.type in ("money", "number"):
        return V.same_amount(a, b)
    if spec.type == "text":
        return V.same_text(a, b)
    return a == b


def _item(schema: Schema, raw: dict, page: int, refs: dict[str, Ref]) -> dict:
    spec = next(s for s in schema.fields.values() if s.type == "list")
    out: dict[str, Any] = {"page": page, "ref": clean_ref(raw.get("ref")), "grounded": True}
    for col, item_spec in spec.item.items():
        printed = raw.get(col)
        value, _ = normalize(item_spec, printed, None)
        out[col] = value
        if printed not in (None, "") and item_spec.type in ("money", "number"):
            if not any(V.text_holds_amount(r.text, str(printed)) for r in refs.values()):
                out["grounded"] = False
    ref = out["ref"]
    out["bbox"] = refs[ref].bbox.as_list() if ref in refs and refs[ref].bbox else None
    return out


def _list_field(name: str, items: list[dict]) -> FieldValue:
    if not items:
        return FieldValue(name=name, value=[], status="missing", reasons=["no lines found"])
    grounded = all(i.get("grounded") for i in items)
    return FieldValue(
        name=name,
        value=[{k: v for k, v in i.items() if k not in ("grounded",)} for i in items],
        page=items[0]["page"],
        ref=items[0].get("ref"),
        bbox=items[0].get("bbox"),
        confidence=0.9 if grounded else 0.5,
        grounded=grounded,
        reasons=[] if grounded else ["a line's figures are not printed on the page"],
    )


# --- rules ---------------------------------------------------------------------------------


def check_rules(schema: Schema, fields: dict[str, FieldValue]) -> list[dict]:
    out = []
    val = {n: f.value for n, f in fields.items() if f.value not in (None, [])}
    for rule in schema.rules:
        passed, detail = True, ""
        k = rule.kind
        if k == "sum":
            parts = [val.get(p) for p in rule.parts]
            total = val.get(rule.total)
            if total is None or any(p is None for p in parts):
                passed, detail = True, "not checked (a field is missing)"
            else:
                s = sum(parts)
                passed = V.same_amount(total, s, rel=rule.tolerance)
                detail = f"{total:,.2f} vs {s:,.2f}"
        elif k == "sum_of_items":
            rows = val.get(rule.of_list) or []
            total = val.get(rule.total)
            amounts = [r.get(rule.column) for r in rows if r.get(rule.column) is not None]
            if total is None or not amounts:
                detail = "not checked (a field is missing)"
            else:
                s = sum(amounts)
                passed = V.same_amount(total, s, rel=rule.tolerance)
                detail = f"{total:,.2f} vs lines {s:,.2f}"
        elif k == "product_of_item":
            bad = []
            for i, r in enumerate(val.get(rule.of_list) or [], start=1):
                factors = [r.get(f) for f in rule.factors]
                result = r.get(rule.result)
                if result is None or any(f is None for f in factors):
                    continue
                prod = 1.0
                for f in factors:
                    prod *= f
                if not V.same_amount(result, prod, rel=rule.tolerance):
                    bad.append(i)
            passed, detail = not bad, (f"lines {bad}" if bad else "")
        elif k == "not_greater":
            a, b = val.get(rule.smaller), val.get(rule.larger)
            if a is not None and b is not None:
                passed, detail = a <= b + 0.01, f"{a:,.2f} vs {b:,.2f}"
        elif k == "date_order":
            a, b = val.get(rule.earlier), val.get(rule.later)
            if a and b:
                passed, detail = str(a) <= str(b), f"{a} vs {b}"
        elif k == "ratio_between":
            num, den = val.get(rule.numerator), val.get(rule.denominator)
            if num is not None and den is not None and den > 0:
                ratio = num / den
                passed = (rule.min is None or ratio >= rule.min) and (rule.max is None or ratio <= rule.max)
                detail = f"{ratio:.2f} (allowed {rule.min} to {rule.max})"
            elif num is not None and den is not None and den < 0 < num and (rule.min or 0) > 0:
                passed, detail = False, "positive after a negative (a profit after tax with a loss before tax)"
            elif num is not None and den is not None:
                detail = "not checked (a loss)"
        elif k == "differ":
            vals = [val.get(f) for f in rule.fields_]
            if all(v is not None for v in vals) and len(vals) == 2:
                passed = not V.same_amount(vals[0], vals[1], rel=1e-9, abs_tol=0.0)
                detail = "" if passed else f"both {vals[0]:,.2f}"
        out.append({"name": rule.name, "passed": passed, "soft": rule.soft, "detail": detail, "fields": rule.fields()})
    return out
