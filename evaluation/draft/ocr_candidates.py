"""Find candidate figures on scanned pages, to be confirmed by eye.

OCR is used only to locate lines that look like table rows (a label followed
by numbers) and to get their boxes. The values themselves are not trusted:
each candidate is rendered as a crop and read by a person (or a reviewer)
before it enters the golden set with ``source = visual``.

Usage:
    python -m evaluation.draft.ocr_candidates <pdf> <out.jsonl> [--dpi 200] [--lang eng]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium

_NUM = re.compile(r"^\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?$|^\(?-?\d+\.\d+\)?$")


def ocr_page(png_path: Path, lang: str) -> list[dict]:
    tsv = subprocess.run(
        ["tesseract", str(png_path), "stdout", "-l", lang, "--psm", "6", "tsv"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout
    rows = list(csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE))
    return [r for r in rows if r.get("level") == "5" and (r.get("text") or "").strip()]


def candidates(pdf: Path, dpi: int, lang: str) -> list[dict]:
    doc = pdfium.PdfDocument(str(pdf))
    scale = dpi / 72.0
    out: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(len(doc)):
            page = doc[i]
            png = Path(tmp) / f"p{i + 1}.png"
            page.render(scale=scale).to_pil().save(png)
            words = ocr_page(png, lang)
            lines: dict[tuple[str, str, str], list[dict]] = {}
            for w in words:
                lines.setdefault((w["block_num"], w["par_num"], w["line_num"]), []).append(w)
            for ws in lines.values():
                ws.sort(key=lambda w: int(w["left"]))
                texts = [w["text"] for w in ws]
                nums = [w for w in ws if _NUM.match(w["text"])]
                if len(nums) < 1:
                    continue
                first = ws.index(nums[0])
                label = " ".join(texts[:first]).strip()
                if len(re.findall(r"[A-Za-zሀ-፿]{3,}", label)) < 1:
                    continue
                for n in nums:
                    x0 = int(n["left"]) / scale
                    top = int(n["top"]) / scale
                    out.append(
                        {
                            "page": i + 1,
                            "label": label[:100],
                            "ocr_value": n["text"],
                            "conf": float(n["conf"]),
                            "bbox": [
                                round(x0, 1),
                                round(top, 1),
                                round(x0 + int(n["width"]) / scale, 1),
                                round(top + int(n["height"]) / scale, 1),
                            ],
                            "line": " ".join(texts)[:200],
                        }
                    )
    doc.close()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--lang", default="eng")
    args = ap.parse_args()
    rows = candidates(args.pdf, args.dpi, args.lang)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{args.pdf.name}: {len(rows)} candidate numbers")


if __name__ == "__main__":
    main()
