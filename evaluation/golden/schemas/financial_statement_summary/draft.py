"""Draft the answers for the financial statement set (a person then reviews them).

For each document: find the statement pages in the extracted text (pages that
print "total assets" and "total liabilities", or a profit line), ask a model
that is NOT the extractor's default (gpt-4.1-mini) to copy the headline
figures of the latest fiscal year exactly as printed, then check every value
mechanically: it must appear on the page it is said to come from, and the
balance sheet must add up. Anything that fails is marked for a person.

    python -m evaluation.golden.schemas.financial_statement_summary.draft --run runs/m8

Writes labels.draft.jsonl next to this file; after review it becomes
labels.jsonl (status "draft" until a person confirms each document).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parents[2]
sys.path.insert(0, str(EVAL.parent))

MONEY = ["total_assets", "total_liabilities", "total_equity", "profit_before_tax", "profit_after_tax"]
_PATTERNS = {
    "balance": [r"total\s+assets", r"total\s+liabilities", r"(?:statement\s+of\s+financial\s+position|balance\s+sheet)"],
    "income": [r"profit\s+before\s+(?:income\s+)?tax", r"profit\s+(?:for\s+the\s+year|after\s+tax)|net\s+profit|loss\s+for\s+the\s+year",
               r"(?:profit\s+or\s+loss|income\s+statement|profit\s+and\s+loss)"],
}

SYSTEM = """You copy figures from financial statements exactly as printed. You never compute.
Return ONLY JSON:
{"entity_name": str, "period_end": "YYYY-MM-DD", "currency": "ETB"|"USD"|...,
 "fields": {"total_assets": {"printed": str|null, "page": int|null, "scale_text": str|null},
            "total_liabilities": {...}, "total_equity": {...}, "profit_before_tax": {...}, "profit_after_tax": {...}},
 "notes": str}
Rules:
- Use the LATEST fiscal year in the document: the current-year column of the statement of financial position
  (balance sheet) and of the income statement, never the comparative (prior-year) column.
- Prefer the primary statements over highlights or summaries. If the document has both "Bank" and "Group"
  columns, use the entity's own (Bank / Company) column.
- "printed" is the number exactly as on the page, with its parentheses or minus sign ("(4,790,941)").
- "scale_text" is how the page states the unit ("Birr'000", "in millions of Birr", "Birr"); null if not stated.
- total_liabilities is the line labelled total liabilities (not liabilities plus equity). total_equity is the
  total equity / capital and reserves / shareholders' funds line.
- profit_after_tax is the profit (or loss) for the year after tax. Use null for any figure the pages do not print.
"""


def scale_of(text: str | None) -> float:
    t = (text or "").lower().replace("’", "'")
    if re.search(r"'?000|thousand|o0o|ooo", t):
        return 1e3
    if "million" in t or re.search(r"\bmn\b|\bm\b", t):
        return 1e6
    if "billion" in t or re.search(r"\bbn\b", t):
        return 1e9
    return 1.0


def parse_printed(s: str | None) -> float | None:
    if not s:
        return None
    neg = "(" in s or s.strip().startswith(("-", "−", "–"))
    digits = re.sub(r"[^\d.]", "", s)
    if not digits:
        return None
    v = float(digits)
    return -v if neg else v


def statement_pages(pages: dict[int, str]) -> list[int]:
    scored = []
    for p, text in pages.items():
        s = 0
        for group in _PATTERNS.values():
            s += sum(bool(re.search(pat, text, re.I)) for pat in group)
        if s >= 2:
            scored.append((s, p))
    best = sorted(scored, key=lambda t: (-t[0], t[1]))[:6]
    return sorted(p for _, p in best)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/m8")
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--docs", default="")
    args = ap.parse_args(argv)
    from dotenv import load_dotenv

    load_dotenv(EVAL.parent / ".env")
    from src.agents.json_util import extract_json
    from src.llm.factory import client_for_request

    llm = client_for_request(args.model)
    docs = json.loads((HERE / "documents.json").read_text(encoding="utf-8"))["documents"]
    wanted = set(args.docs.split(",")) if args.docs else None
    out_path = HERE / "labels.draft.jsonl"
    done = {}
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["doc_key"]] = row
    for d in docs:
        key = d["doc_key"]
        if (wanted and key not in wanted) or (key in done and not wanted):
            continue
        ext = EVAL / args.run / "extraction" / f"{key}.json"
        if not ext.exists():
            print(f"{key}: not ingested yet")
            continue
        pages = {int(k): v for k, v in json.loads(ext.read_text(encoding="utf-8"))["pages_text"].items()}
        chosen = statement_pages(pages)
        first = [p for p in sorted(pages)[:2] if p not in chosen]
        blob = "\n\n".join(f"=== page {p} ===\n{pages[p][:9000]}" for p in first + chosen)
        res = llm.complete(f"document: {d['file_name']}\n\n{blob}\n\nReturn the JSON now.", system=SYSTEM,
                           response_format="json", temperature=0.0, max_tokens=900)
        data = extract_json(res.text)
        fields, issues = {}, []
        for name in MONEY:
            f = (data.get("fields") or {}).get(name) or {}
            printed, page = f.get("printed"), f.get("page")
            value = parse_printed(printed)
            if value is not None:
                value *= scale_of(f.get("scale_text"))
                text = pages.get(int(page or 0), "")
                if printed and re.sub(r"[^\d]", "", printed) not in re.sub(r"[^\d]", "", text):
                    issues.append(f"{name}: '{printed}' not found on page {page}")
            fields[name] = {"value": value, "printed": printed, "page": page, "scale_text": f.get("scale_text")}
        a, liab, eq = (fields[k]["value"] for k in ("total_assets", "total_liabilities", "total_equity"))
        if None not in (a, liab, eq) and abs(a - (liab + eq)) > 0.01 * abs(a):
            issues.append(f"balance sheet does not add up: {a} vs {liab} + {eq}")
        row = {
            "doc_key": key,
            "schema": "financial_statement_summary",
            "fields": {
                "entity_name": data.get("entity_name"),
                "period_end": data.get("period_end"),
                "currency": data.get("currency"),
                **{k: v["value"] for k, v in fields.items()},
            },
            "evidence": {k: {"printed": v["printed"], "page": v["page"], "scale_text": v["scale_text"]} for k, v in fields.items()},
            "pages_read": first + chosen,
            "issues": issues,
            "notes": data.get("notes", ""),
            "status": "draft",
            "drafted_by": args.model,
        }
        done[key] = row
        print(f"{key}: {row['fields']} issues={issues}", flush=True)
        out_path.write_text("".join(json.dumps(done[k], ensure_ascii=False) + "\n" for k in sorted(done)), encoding="utf-8")


if __name__ == "__main__":
    main()
