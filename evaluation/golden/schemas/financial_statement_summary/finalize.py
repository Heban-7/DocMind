"""Turn the drafted answers into labels.jsonl, with the corrections a reviewer made.

Each correction says what the page shows and why the draft was wrong (usually
an OCR misreading, or a scale the draft missed). Every document stays
"draft" until a person confirms it in the review sheet.

    python -m evaluation.golden.schemas.financial_statement_summary.finalize
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
K = 1000.0

# doc_key -> (field corrections, accepted alternatives, note)
CORRECTIONS: dict[str, tuple[dict, dict, str]] = {
    "dbe_audit_2023": (
        {"total_assets": 160_155_100 * K, "total_liabilities": 123_085_898 * K, "total_equity": 37_069_202 * K,
         "profit_before_tax": 6_463_494 * K, "profit_after_tax": 5_737_998 * K},
        {"total_assets": [160_155_807 * K], "total_liabilities": [123_086_112 * K], "total_equity": [37_069_694 * K],
         "profit_before_tax": [6_463_536 * K], "profit_after_tax": [5_738_040 * K]},
        "Statements in Birr'000 (the draft missed the scale). The Bank column is the answer; the Group column is accepted (p11, p12).",
    ),
    "audited_fs_2019": (
        {"total_assets": 77_874_337 * K, "total_liabilities": 70_762_151 * K, "total_equity": 7_112_185 * K},
        {},
        "Birr'000. Total equity is 7,112,185 on the page image; the OCR text reads '2:112,185' (p2).",
    ),
    "audited_fs_2020": (
        {"entity_name": "Ethio Telecom", "profit_after_tax": 9_453_072 * K},
        {},
        "Profit after tax is 9,453,072 on the page image; the OCR text reads 9,433,072 (p1).",
    ),
    "audited_fs_2022": (
        {"total_assets": 189_017_711 * K, "total_liabilities": 87_462_761 * K, "total_equity": 101_554_950 * K,
         "profit_after_tax": 8_999_582 * K},
        {},
        "Birr'000. Total equity 101,554,950 and profit after tax 8,999,582 are on the page images; the OCR text lost them (p1, p2).",
    ),
    "ethiore_2022": (
        {"profit_after_tax": 223_523_541.0},
        {},
        "Profit after tax is 223,523,541 (Total column) on the page image; the OCR text reads 233,523,541 (p42).",
    ),
}


def main() -> None:
    docs = json.loads((HERE / "documents.json").read_text(encoding="utf-8"))["documents"]
    keys = [d["doc_key"] for d in docs]
    drafts = {}
    for line in (HERE / "labels.draft.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            drafts[row["doc_key"]] = row
    out = []
    for key in keys:
        if key not in drafts:
            print(f"{key}: no draft yet")
            continue
        row = drafts[key]
        fields = dict(row["fields"])
        fields["currency"] = "ETB" if fields.get("currency") and "birr" in str(fields["currency"]).lower() or fields.get("currency") in ("ETB",) else fields.get("currency")
        fix, accept, note = CORRECTIONS.get(key, ({}, {}, ""))
        fields.update(fix)
        a, liab, eq = fields.get("total_assets"), fields.get("total_liabilities"), fields.get("total_equity")
        balanced = None if None in (a, liab, eq) else abs(a - (liab + eq)) <= 0.01 * abs(a)
        out.append({
            "doc_key": key,
            "schema": "financial_statement_summary",
            "fields": fields,
            "accept": accept,
            "evidence": row.get("evidence", {}),
            "status": "draft",
            "reviewed": "values checked against the page text; corrected ones against the page image",
            "note": note,
            "balance_sheet_adds_up": balanced,
        })
        print(f"{key}: {'corrected - ' + note[:60] if note else 'as drafted'} | balanced={balanced}")
    (HERE / "labels.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print(f"{len(out)} documents written")


if __name__ == "__main__":
    main()
