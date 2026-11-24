# DocMind evaluation suite

One harness scores every version of DocMind against the same golden set, so each
milestone can show before-and-after numbers. Scores are deterministic: no LLM
judges anything, so a number never drifts between runs and every pass or fail
can be traced to a page.

## Golden set v1

`golden/v1/` holds 25 documents (1,237 pages) from the project corpus:

| Class | Documents | What it tests |
| --- | --- | --- |
| A, annual reports | 7 | Multi-column financial reports with statement tables |
| B, scanned | 6 | Image-only PDFs: OCR and vision paths |
| C, mixed technical | 4 | Narrative plus tables and charts |
| D, table-heavy | 5 | Fiscal and statistical tables |
| E, Amharic scans | 3 | Ethiopic script on scanned government forms |

Files:

- `documents.json`: each document's file name, SHA-256, page count and class. PDFs are not committed (`data/` is git-ignored); a run refuses a file whose hash differs.
- `figures.jsonl`: key figures with value, sign, stated scale, page and, for digital pages, the number's box. Figures drafted from a PDF's own text layer carry `source = text_layer`; figures read by eye from rendered scans carry `source = visual`.
- `questions.jsonl`: lookups, percentage changes (computed from two gold figures), list questions, and questions the document cannot answer.
- `manual_figures.json`, `manual_questions.json`: the hand-entered part, generated from `draft/manual_v1.py`.
- `review_sheet.csv`: the sheet a person uses to confirm or correct the drafts.

Every item starts as `draft`. Reviewed items become `confirmed`, `corrected` or `rejected` (excluded from scoring), and reports state how many figures a person has confirmed.

## Running

```bash
# needs the dev database: docker compose -f docker-compose.dev.yml up -d db
# raw outputs go to evaluation/runs/<name>/ (git-ignored); each run has its own Postgres account
python -m evaluation.run extract --run runs/m3
python -m evaluation.run qa      --run runs/m3
python -m evaluation.run score   --run runs/m3 --name "M3" --publish m3-postgres
```

`--publish` copies the report to `reports/`. The corpus folder defaults to `data/data` (override with `DOCMIND_CORPUS_DIR`). Set `DOCMIND_EVAL_REUSE_MODELS` to a folder of saved document models to skip extraction when only later stages changed (see `systems/current.py`).

### Speed on a small server

```bash
# the product as it ships: API + worker processes pinned to 2 CPU cores, CPU only
python -m evaluation.speed --mode worker --run runs/m4-speed/after
# older code where the upload request ran the whole ingest (e.g. an export of commit 920d19b)
python -m evaluation.speed --mode sync --code <folder> --run runs/m4-speed/before --env DOCMIND_NUM_THREADS=2
```

Each run gets a fresh database. It records time to ready, time until the document is first searchable, and API latency (`/health` and a database read every 250 ms) while the document is read.

The V1 baseline (`reports/v1-baseline.*`) and the M2 run (`reports/m2-v2-extraction.*`) were produced with systems `v1` and `v2`, which were removed with the old storage in M3; check out commit `9d8509f` to rerun them.

## Metrics

| Metric | How it is scored |
| --- | --- |
| Page coverage | Pages with at least 20 characters of extracted text, versus pages silently missing |
| Figure intact on page | The gold number appears as one token on the gold page of the extraction |
| Split digits | The number only appears once spaces inside it are removed (`1 82,044`) |
| Row integrity | The row label and the value sit on the same extracted line or table row |
| Fact correct | The system's fact table holds the gold value, with its sign, on that page |
| Answer correct | Numbers: the answer states the gold value (within 0.5%, or 2% for computed changes), with the right sign. Lists: at least 80% of items named. Unanswerable: the answer refuses. |
| Citation precision | Share of an answer's citations that point at a gold page |
| Retrieval hit@5 | A gold page is among the pages of the top 5 retrieved chunks |
| Latency, cost | Wall time per question; tokens and cost counted at the provider client |

## Reviewing the golden set

```bash
python -m evaluation.review export              # refresh review_sheet.csv
# fill the status column, then:
python -m evaluation.review import golden/v1/review_sheet.csv
```

Start with rows marked `sample = yes`: every Amharic item and a fixed 20% sample of the rest.
