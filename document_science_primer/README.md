# Phase 0 — Document Science Primer

A read-only **sandbox** for understanding what lives inside a PDF *before* we
build any pipeline. Nothing here classifies documents or makes routing
decisions — it only **observes** and **compares**.

## Files

| File | Role |
|------|------|
| `explore_pdf.py` | Reusable toolkit + script. Inspects one page: size, raw character count, words, and word bounding boxes (`x0/y0/x1/y1`). |
| `compare_extractors.py` | Bake-off script. **Reuses** `explore_pdf.py`'s pdfplumber logic and pits it against Docling (AI layout-aware) on the same pages. |
| `__init__.py` | Marks the folder as an importable package. |

## How the pieces connect

`compare_extractors.py` imports the shared paths and pdfplumber extraction
from `explore_pdf.py`, so the extraction logic is defined **exactly once**:

```
explore_pdf.py  --(extract_text_with_pdfplumber, SAMPLE_PDF, PROJECT_ROOT)-->  compare_extractors.py
```

## How to run

From the project root:

```bash
# Step 1 — inspect a single page
uv run phase_0_document_science_primer/explore_pdf.py

# Step 2 — compare pdfplumber vs. Docling
uv run phase_0_document_science_primer/compare_extractors.py
```

Both scripts read `data/data/sample.pdf` (paths resolve from the project root,
so you can launch them from anywhere). The comparison writes full outputs to
`playground_output/` for side-by-side review.

To explore a different document, copy any corpus PDF over the sample:

```bash
cp "data/data/CBE ANNUAL REPORT 2023-24.pdf" "data/data/sample.pdf"
```
