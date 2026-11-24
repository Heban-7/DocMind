# M6: retrieval v2 (hybrid search)

Golden set v1: 25 documents, 1237 pages, 184 figures, 142 questions (0 figures confirmed by a person so far).
Generated 2026-11-24T13:29:36+00:00 on Intel64 Family 6 Model 186 Stepping 2, GenuineIntel; M6: hybrid search (pgvector + Postgres full-text with quoted labels and table references as phrase votes, reciprocal rank fusion) over chunks embedded with their document title and section path; full chunk text to the answer step; PageIndex in document order; cross-encoder reranker measured and left off (answers in top 5 81.2% -> 76.9%, +3.6 s per question on CPU); extraction reused from the M4 run (unchanged); answers by gpt-4o-mini. Retrieval alone (python -m evaluation.run retrieval), M5 vectors -> M6 hybrid: hit@1 44.4% -> 57.3%, hit@5 76.1% -> 82.9%, MRR 0.567 -> 0.661, answer in the top 5 chunks 74.4% -> 87.2%

## Extraction

| Metric | Value |
| --- | --- |
| Pages with extracted content | 1226 of 1237 (99.1%) |
| Pages silently missing (no content, no failure flag) | 0 |
| Gold figures intact on the right page | 97.3% |
| Gold figures with digits split by spaces | 0.0% |
| Gold figures missing from the whole extraction | 2.2% |
| Gold figures found only on another page | 0.5% |
| Label and value on the same row (table row integrity) | 80.4% |
| FactTable holds the right value | 94.6% |
| FactTable holds the figure with a wrong value | 0.0% |
| ...with the right sign, scale and unit (typed facts, M5) | 90.8% |
| ...of the figures intact on their page | 93.3% |
| ...and labels and period that identify it | 69.0% |
| Ingest time, all documents | 3702.0 s |
| Ingest API cost, all documents | $0.1893 |

**By document class**

| Class | Figures | Intact on page | Split digits | Missing | Row intact | Fact correct |
| --- | --- | --- | --- | --- | --- | --- |
| A_annual_report | 76 | 100.0% | 0.0% | 0.0% | 93.4% | 97.4% |
| B_scanned | 34 | 94.1% | 0.0% | 2.9% | 61.8% | 88.2% |
| C_mixed_technical | 26 | 100.0% | 0.0% | 0.0% | 92.3% | 100.0% |
| D_table_heavy | 39 | 100.0% | 0.0% | 0.0% | 82.1% | 100.0% |
| E_amharic_scanned | 9 | 66.7% | 0.0% | 33.3% | 0.0% | 55.6% |

**Speed by engine** (extraction stage, per page that produced content; for page-level routing, per page by the engine that read it)

| Engine | Pages | Seconds per page | p95 | Device |
| --- | --- | --- | --- | --- |
| docling | 293 | 2.67 | 4.96 | cuda x1 lanes |
| ocr | 398 | 5.41 | 9.49 | cuda x1 lanes |
| text_layer | 512 | 0.28 | 0.66 | cuda x1 lanes |
| vision | 34 | 10.02 | 15.19 | cuda x1 lanes |

Pages flagged for a person to check: 93

**Per document**

| Document | Class | Pages | Engine | Content pages | Silently missing | Extract s | s per extracted page | Facts | Cost $ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cbe_2023_24 | A | 161 | docling:100, ocr:11, text_layer:49, vision:1 | 161 | 0 | 403.5 | 2.51 | 6258 | 0.0075 |
| ethiore_2017 | A | 104 | docling:28, ocr:11, text_layer:61, vision:4 | 101 | 0 | 181.7 | 1.8 | 1700 | 0.0167 |
| ets_2023_24 | A | 92 | docling:26, ocr:11, text_layer:48, vision:7 | 91 | 0 | 192.2 | 2.11 | 1482 | 0.04 |
| ethswitch_10th_2023_24 | A | 80 | docling:5, ocr:44, text_layer:28, vision:3 | 76 | 0 | 271.6 | 3.57 | 1226 | 0.0174 |
| ethswitch_2021_22 | A | 84 | docling:30, ocr:3, text_layer:49, vision:2 | 84 | 0 | 109.7 | 1.31 | 1643 | 0.0121 |
| cbe_2006_07 | A | 60 | docling:33, ocr:8, text_layer:19 | 59 | 0 | 157.7 | 2.67 | 1901 | 0.0006 |
| ethiore_profile_2024_25 | A | 24 | docling:2, ocr:1, text_layer:18, vision:3 | 24 | 0 | 38.8 | 1.62 | 179 | 0.0118 |
| dbe_audit_2023 | B | 95 | ocr:93, text_layer:1, vision:1 | 95 | 0 | 671.8 | 7.07 | 4461 | 0.0074 |
| cbe_2010_11 | B | 62 | ocr:56, vision:6 | 61 | 0 | 252.6 | 4.14 | 887 | 0.0342 |
| cbe_2009_10 | B | 38 | ocr:37, vision:1 | 38 | 0 | 367.7 | 9.68 | 1268 | 0.006 |
| ethswitch_2019 | B | 70 | ocr:66, vision:4 | 69 | 0 | 347.9 | 5.04 | 921 | 0.023 |
| audited_fs_2021 | B | 3 | ocr:3 | 3 | 0 | 29.5 | 9.84 | 231 | 0.0 |
| security_disclosure | B | 15 | ocr:15 | 15 | 0 | 74.6 | 4.97 | 19 | 0.0001 |
| fta_survey_2022 | C | 155 | docling:14, ocr:6, text_layer:135 | 155 | 0 | 121.9 | 0.79 | 1856 | 0.0014 |
| pharma_2019 | C | 15 | ocr:1, text_layer:13, vision:1 | 15 | 0 | 14.7 | 0.98 | 42 | 0.0056 |
| ethiore_2019 | C | 32 | docling:2, ocr:21, text_layer:9 | 32 | 0 | 123.6 | 3.86 | 526 | 0.0003 |
| cbe_2012_13 | C | 20 | docling:8, ocr:2, text_layer:9, vision:1 | 20 | 0 | 31.8 | 1.59 | 298 | 0.0041 |
| tax_exp_2021_22 | D | 60 | docling:25, text_layer:35 | 60 | 0 | 111.3 | 1.86 | 2063 | 0.0006 |
| tax_exp_sample | D | 20 | docling:6, text_layer:14 | 20 | 0 | 14.9 | 0.74 | 275 | 0.0002 |
| cpi_2025_08 | D | 13 | docling:5, text_layer:8 | 13 | 0 | 17.3 | 1.33 | 250 | 0.0001 |
| cpi_2025_03 | D | 12 | docling:4, text_layer:8 | 12 | 0 | 16.2 | 1.35 | 223 | 0.0001 |
| cpi_2025_06 | D | 13 | docling:5, text_layer:8 | 13 | 0 | 16.2 | 1.25 | 248 | 0.0001 |
| am_audit_findings | E | 3 | ocr:3 | 3 | 0 | 12.3 | 4.09 | 5 | 0.0 |
| am_procurement | E | 3 | ocr:3 | 3 | 0 | 15.6 | 5.18 | 21 | 0.0 |
| am_budget | E | 3 | ocr:3 | 3 | 0 | 18.0 | 6.01 | 63 | 0.0 |

## Retrieval and answers

| Metric | Value |
| --- | --- |
| Questions answered correctly | 76.8% of 142 |
| Answerable questions answered correctly | 78.6% |
| False refusals on answerable questions | 0.0% |
| Unanswerable questions correctly refused | 68.0% |
| Retrieval: a gold page in the top 5 | 82.9% |
| Citation precision (share of citations on a gold page) | 0.233 |
| Answers citing at least one gold page | 78.6% |
| Latency p50 / p95 | 10.6 s / 15.05 s |
| Time to first token, p50 | 10.6 s |
| LLM calls per question | 3 |
| Cost per question | $0.000872 |
| Errors | 0 |

| Question type | Questions | Correct | False refusals | Retrieval hit@5 | Citation precision |
| --- | --- | --- | --- | --- | --- |
| change_percent | 14 | 85.7% | 0.0% | 78.6% | 0.495 |
| list | 6 | 66.7% | 0.0% | 83.3% | 0.238 |
| lookup_number | 97 | 78.4% | 0.0% | 83.5% | 0.195 |
| unanswerable | 25 | 68.0% | n/a | n/a | n/a |

| Document class | Questions | Correct | Retrieval hit@5 |
| --- | --- | --- | --- |
| A_annual_report | 42 | 85.7% | 85.7% |
| B_scanned | 35 | 68.6% | 79.3% |
| C_mixed_technical | 21 | 81.0% | 88.2% |
| D_table_heavy | 30 | 83.3% | 72.0% |
| E_amharic_scanned | 14 | 50.0% | 100.0% |

## How to reproduce

```
python -m evaluation.run extract --run runs/<name>
python -m evaluation.run qa --run runs/<name>
python -m evaluation.run score --run runs/<name>
```

Scores are deterministic (no LLM judge). Golden figures marked `draft` have not yet been confirmed by a person.
