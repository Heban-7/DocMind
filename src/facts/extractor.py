"""
Heuristic (+ optional LLM) fact extractor for numerical / table LDUs.

Pulls metric-value-period triples from prose and Markdown tables so the
FactTable can answer precise fiscal questions without LLM number invention.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from src.chunking.models import DocumentChunk
from src.facts.models import FactRecord
from src.facts.store import FactStore
from src.pageindex.builder import load_chunks_jsonl
from src.config import CHUNKS_DIR

logger = logging.getLogger("docmind.facts")

# FY 2020/21 | Q3 2024 | 2018/19
_PERIOD = re.compile(
    r"\b(?:FY\s*)?\d{4}\s*/\s*\d{2,4}\b|\bQ[1-4]\s+\d{4}\b|\bFY\s*\d{4}\b",
    re.IGNORECASE,
)

# ETB 120.7 billion | $4.2B | 2.8% | 37%
_AMOUNT = re.compile(
    r"(?P<currency>ETB|USD|US\$|\$|EUR|GBP)?\s*"
    r"(?P<number>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<scale>billion|million|trillion|bn|mn)?\s*"
    r"(?P<unit_suffix>%|percent|per\s*cent)?",
    re.IGNORECASE,
)

# "Import tax expenditures were ETB 120.7 billion in FY 2020/21"
_PROSE_FACT = re.compile(
    r"(?P<metric>[A-Za-z][^.]{2,160}?)\s+"
    r"(?:were|was|totalled|totaled|reached|amounted to|represented|constituted)\s+"
    r"(?P<value_span>"
    r"(?:ETB|USD|US\$|\$|EUR|GBP)?\s*"
    r"\d{1,3}(?:,\d{3})*(?:\.\d+)?"
    r"(?:\s*(?:billion|million|trillion|bn|mn))?"
    r"(?:\s*(?:%|percent))?"
    r")"
    r"(?:\s+(?:in|for|during)\s+(?P<period>"
    r"(?:FY\s*)?\d{4}\s*/\s*\d{2,4}|Q[1-4]\s+\d{4}|FY\s*\d{4}"
    r"))?",
    re.IGNORECASE,
)

_NUMERIC_CELL = re.compile(
    r"^\s*(?:ETB|USD|\$)?\s*\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*"
    r"(?:billion|million|%)?\s*$",
    re.IGNORECASE,
)


def _parse_number(raw: str) -> float | None:
    cleaned = raw.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_unit(currency: str, scale: str, suffix: str) -> str:
    parts: list[str] = []
    cur = (currency or "").strip().replace("US$", "$")
    if cur:
        parts.append(cur.upper() if cur != "$" else "USD")
    if scale:
        full = {"bn": "billion", "mn": "million"}.get(scale.lower(), scale.lower())
        parts.append(full)
    if suffix:
        parts.append("%" if "%" in suffix or "percent" in suffix.lower() else suffix)
    return " ".join(parts).strip()


def _clean_metric(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" :,-")
    # Drop leading articles / weak verbs leftovers
    text = re.sub(
        r"^(?:the|a|an)\s+", "", text, flags=re.IGNORECASE
    )
    return text[:160]


def _page(chunk: DocumentChunk) -> int:
    pages = chunk.metadata.page_numbers
    return pages[0] if pages else 1


def extract_facts_from_prose(
    chunk: DocumentChunk, *, doc_id: str, document_name: str
) -> list[FactRecord]:
    """Regex-based facts from narrative sentences."""
    facts: list[FactRecord] = []
    text = chunk.text
    for match in _PROSE_FACT.finditer(text):
        metric = _clean_metric(match.group("metric"))
        value_span = match.group("value_span").strip()
        period = (match.group("period") or "").strip()
        if not period:
            nearby = text[max(0, match.start() - 40) : match.end() + 80]
            period_match = _PERIOD.search(nearby)
            period = period_match.group(0) if period_match else ""

        amount = _AMOUNT.search(value_span)
        if not amount:
            continue
        value = _parse_number(amount.group("number"))
        unit = _normalize_unit(
            amount.group("currency") or "",
            amount.group("scale") or "",
            amount.group("unit_suffix") or "",
        )
        excerpt = match.group(0).strip()
        if len(excerpt) > 240:
            excerpt = excerpt[:237] + "..."
        facts.append(
            FactRecord(
                doc_id=doc_id,
                document_name=document_name,
                metric=metric,
                value=value,
                value_text=value_span,
                unit=unit,
                period=period,
                page_number=_page(chunk),
                content_hash=chunk.metadata.content_hash,
                chunk_id=chunk.id,
                source_excerpt=excerpt,
                extractor="heuristic",
            )
        )
    return facts


def extract_facts_from_table(
    chunk: DocumentChunk, *, doc_id: str, document_name: str
) -> list[FactRecord]:
    """Pull numeric cells from Markdown tables (label column + value columns)."""
    lines = [
        ln.strip()
        for ln in chunk.text.splitlines()
        if ln.strip().startswith("|") and not re.match(r"^\|\s*[-:| ]+\|$", ln.strip())
    ]
    if len(lines) < 2:
        return []

    def cells(line: str) -> list[str]:
        parts = [c.strip() for c in line.strip("|").split("|")]
        return parts

    header = cells(lines[0])
    facts: list[FactRecord] = []
    section = (
        chunk.metadata.parent_hierarchy[-1]
        if chunk.metadata.parent_hierarchy
        else "table"
    )

    for line in lines[1:]:
        row = cells(line)
        if not row:
            continue
        label = row[0]
        if not label or label.lower() in {"metric", "item", "category", ""}:
            continue
        for col_idx, cell in enumerate(row[1:], start=1):
            if not cell or not _NUMERIC_CELL.match(cell):
                # also accept amounts with currency words
                if not _AMOUNT.search(cell):
                    continue
            amount = _AMOUNT.search(cell)
            if not amount:
                continue
            value = _parse_number(amount.group("number"))
            unit = _normalize_unit(
                amount.group("currency") or "",
                amount.group("scale") or "",
                amount.group("unit_suffix") or "",
            )
            col_name = header[col_idx] if col_idx < len(header) else f"col_{col_idx}"
            # Skip TOC-like page-number-only columns
            if re.fullmatch(r"\d{1,3}", cell.strip()) and "page" in col_name.lower():
                continue
            period = ""
            period_match = _PERIOD.search(col_name) or _PERIOD.search(label)
            if period_match:
                period = period_match.group(0)
            metric = _clean_metric(f"{label} ({col_name})" if col_name else label)
            if section and section.lower() not in metric.lower():
                metric = _clean_metric(f"{section}: {metric}")
            facts.append(
                FactRecord(
                    doc_id=doc_id,
                    document_name=document_name,
                    metric=metric,
                    value=value,
                    value_text=cell.strip(),
                    unit=unit,
                    period=period,
                    page_number=_page(chunk),
                    content_hash=chunk.metadata.content_hash,
                    chunk_id=chunk.id,
                    source_excerpt=f"{label} | {cell.strip()}",
                    extractor="heuristic",
                )
            )
    return facts


def extract_facts_from_chunk(
    chunk: DocumentChunk, *, doc_id: str, document_name: str = ""
) -> list[FactRecord]:
    """Extract facts from one LDU (table-aware + prose)."""
    facts: list[FactRecord] = []
    if chunk.metadata.chunk_type in {"table", "mixed"} or "|" in chunk.text:
        facts.extend(
            extract_facts_from_table(
                chunk, doc_id=doc_id, document_name=document_name
            )
        )
    facts.extend(
        extract_facts_from_prose(chunk, doc_id=doc_id, document_name=document_name)
    )
    return facts


def extract_facts_llm(
    chunk: DocumentChunk,
    *,
    doc_id: str,
    document_name: str,
    client,
) -> list[FactRecord]:
    """Optional enrichment: ask a cheap LLM for JSON facts (best-effort)."""
    prompt = (
        "Extract numerical facts from this document excerpt as a JSON array. "
        "Each item: "
        '{"metric": str, "value": number|null, "value_text": str, '
        '"unit": str, "period": str}. '
        "Return [] if none. JSON only.\n\n"
        f"Excerpt:\n{chunk.text[:2000]}"
    )
    try:
        result = client.complete(
            prompt, response_format="json", temperature=0.0, max_tokens=800
        )
        raw = (result.text or "").strip()
        if "```" in raw:
            raw = raw.replace("```json", "```").split("```")[1].strip()
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1:
            return []
        data = json.loads(raw[start : end + 1])
    except Exception as exc:  # pragma: no cover
        logger.warning("LLM fact extract failed: %s", exc)
        return []

    facts: list[FactRecord] = []
    if not isinstance(data, list):
        return []
    for item in data:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric", "")).strip()
        value_text = str(item.get("value_text") or item.get("value") or "").strip()
        if not metric or not value_text:
            continue
        value = item.get("value")
        try:
            value_f = float(value) if value is not None else None
        except (TypeError, ValueError):
            value_f = _parse_number(str(value_text))
        facts.append(
            FactRecord(
                doc_id=doc_id,
                document_name=document_name,
                metric=_clean_metric(metric),
                value=value_f,
                value_text=value_text,
                unit=str(item.get("unit") or ""),
                period=str(item.get("period") or ""),
                page_number=_page(chunk),
                content_hash=chunk.metadata.content_hash,
                chunk_id=chunk.id,
                source_excerpt=value_text[:240],
                extractor="llm",
            )
        )
    return facts


@dataclass
class FactExtractResult:
    doc_id: str
    facts_written: int
    facts_total_for_doc: int


def extract_and_store(
    chunks: list[DocumentChunk],
    *,
    doc_id: str,
    document_name: str = "",
    store: FactStore | None = None,
    use_llm: bool = False,
    llm_client=None,
) -> FactExtractResult:
    """Extract facts from LDUs and replace the FactTable rows for ``doc_id``."""
    store = store or FactStore()
    all_facts: list[FactRecord] = []
    for chunk in chunks:
        all_facts.extend(
            extract_facts_from_chunk(
                chunk, doc_id=doc_id, document_name=document_name
            )
        )
        if use_llm and llm_client is not None:
            all_facts.extend(
                extract_facts_llm(
                    chunk,
                    doc_id=doc_id,
                    document_name=document_name,
                    client=llm_client,
                )
            )

    # Deduplicate by (metric, value_text, period, page)
    seen: set[tuple] = set()
    unique: list[FactRecord] = []
    for fact in all_facts:
        key = (
            fact.metric.lower(),
            fact.value_text.lower(),
            fact.period.lower(),
            fact.page_number,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(fact)

    written = store.replace_doc_facts(doc_id, unique)
    return FactExtractResult(
        doc_id=doc_id,
        facts_written=written,
        facts_total_for_doc=store.count(doc_id),
    )


def extract_and_store_from_chunks_file(
    doc_id: str,
    *,
    document_name: str = "",
    chunks_dir=None,
    store: FactStore | None = None,
    use_llm: bool = False,
    llm_client=None,
) -> FactExtractResult:
    """Load ``.refinery/chunks/{doc_id}.jsonl`` and populate the FactTable."""
    from pathlib import Path

    path = Path(chunks_dir or CHUNKS_DIR) / f"{doc_id}.jsonl"
    chunks = load_chunks_jsonl(path)
    return extract_and_store(
        chunks,
        doc_id=doc_id,
        document_name=document_name,
        store=store,
        use_llm=use_llm,
        llm_client=llm_client,
    )
