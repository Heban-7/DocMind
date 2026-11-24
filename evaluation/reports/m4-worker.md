# M4: background worker and parallel extraction

Golden set v1: 25 documents, 1237 pages, 184 figures, 142 questions (0 figures confirmed by a person so far).
Generated 2026-11-24T09:29:55+00:00 on Intel64 Family 6 Model 186 Stepping 2, GenuineIntel; M4: background worker, Docling with the pypdfium2 backend and balanced page batches, text-layer preview index (commit dfe34e5); full extraction re-run on the RTX 4060 laptop GPU with TableFormer accurate (as M2) to check that quality did not drop; answers by the default text model (gpt-4o-mini). Speed on 2 CPU cores is measured separately in reports/m4-speed.md

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
| FactTable holds the right value | 56.0% |
| FactTable holds the figure with a wrong value | 4.9% |
| Ingest time, all documents | 3694.1 s |
| Ingest API cost, all documents | $0.1911 |

**By document class**

| Class | Figures | Intact on page | Split digits | Missing | Row intact | Fact correct |
| --- | --- | --- | --- | --- | --- | --- |
| A_annual_report | 76 | 100.0% | 0.0% | 0.0% | 93.4% | 75.0% |
| B_scanned | 34 | 94.1% | 0.0% | 2.9% | 61.8% | 38.2% |
| C_mixed_technical | 26 | 100.0% | 0.0% | 0.0% | 92.3% | 73.1% |
| D_table_heavy | 39 | 100.0% | 0.0% | 0.0% | 82.1% | 30.8% |
| E_amharic_scanned | 9 | 66.7% | 0.0% | 33.3% | 0.0% | 22.2% |

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
| cbe_2023_24 | A | 161 | docling:100, ocr:11, text_layer:49, vision:1 | 161 | 0 | 403.5 | 2.51 | 3281 | 0.0084 |
| ethiore_2017 | A | 104 | docling:28, ocr:11, text_layer:61, vision:4 | 101 | 0 | 181.7 | 1.8 | 1091 | 0.0166 |
| ets_2023_24 | A | 92 | docling:26, ocr:11, text_layer:48, vision:7 | 91 | 0 | 192.2 | 2.11 | 605 | 0.0401 |
| ethswitch_10th_2023_24 | A | 80 | docling:5, ocr:44, text_layer:28, vision:3 | 76 | 0 | 271.6 | 3.57 | 526 | 0.0175 |
| ethswitch_2021_22 | A | 84 | docling:30, ocr:3, text_layer:49, vision:2 | 84 | 0 | 109.7 | 1.31 | 654 | 0.0124 |
| cbe_2006_07 | A | 60 | docling:33, ocr:8, text_layer:19 | 59 | 0 | 157.7 | 2.67 | 1109 | 0.0007 |
| ethiore_profile_2024_25 | A | 24 | docling:2, ocr:1, text_layer:18, vision:3 | 24 | 0 | 38.8 | 1.62 | 12 | 0.0118 |
| dbe_audit_2023 | B | 95 | ocr:93, text_layer:1, vision:1 | 95 | 0 | 671.8 | 7.07 | 3052 | 0.0073 |
| cbe_2010_11 | B | 62 | ocr:56, vision:6 | 61 | 0 | 252.6 | 4.14 | 177 | 0.0342 |
| cbe_2009_10 | B | 38 | ocr:37, vision:1 | 38 | 0 | 367.7 | 9.68 | 444 | 0.0059 |
| ethswitch_2019 | B | 70 | ocr:66, vision:4 | 69 | 0 | 347.9 | 5.04 | 551 | 0.023 |
| audited_fs_2021 | B | 3 | ocr:3 | 3 | 0 | 29.5 | 9.84 | 164 | 0.0 |
| security_disclosure | B | 15 | ocr:15 | 15 | 0 | 74.6 | 4.97 | 1 | 0.0001 |
| fta_survey_2022 | C | 155 | docling:14, ocr:6, text_layer:135 | 155 | 0 | 121.9 | 0.79 | 465 | 0.0016 |
| pharma_2019 | C | 15 | ocr:1, text_layer:13, vision:1 | 15 | 0 | 14.7 | 0.98 | 1 | 0.0056 |
| ethiore_2019 | C | 32 | docling:2, ocr:21, text_layer:9 | 32 | 0 | 123.6 | 3.86 | 324 | 0.0004 |
| cbe_2012_13 | C | 20 | docling:8, ocr:2, text_layer:9, vision:1 | 20 | 0 | 31.8 | 1.59 | 151 | 0.0041 |
| tax_exp_2021_22 | D | 60 | docling:25, text_layer:35 | 60 | 0 | 111.3 | 1.86 | 1412 | 0.0008 |
| tax_exp_sample | D | 20 | docling:6, text_layer:14 | 20 | 0 | 14.9 | 0.74 | 141 | 0.0003 |
| cpi_2025_08 | D | 13 | docling:5, text_layer:8 | 13 | 0 | 17.3 | 1.33 | 154 | 0.0001 |
| cpi_2025_03 | D | 12 | docling:4, text_layer:8 | 12 | 0 | 16.2 | 1.35 | 150 | 0.0001 |
| cpi_2025_06 | D | 13 | docling:5, text_layer:8 | 13 | 0 | 16.2 | 1.25 | 155 | 0.0001 |
| am_audit_findings | E | 3 | ocr:3 | 3 | 0 | 12.3 | 4.09 | 0 | 0.0 |
| am_procurement | E | 3 | ocr:3 | 3 | 0 | 15.6 | 5.18 | 0 | 0.0 |
| am_budget | E | 3 | ocr:3 | 3 | 0 | 18.0 | 6.01 | 43 | 0.0 |

## Retrieval and answers

| Metric | Value |
| --- | --- |
| Questions answered correctly | 25.4% of 142 |
| Answerable questions answered correctly | 11.1% |
| False refusals on answerable questions | 82.9% |
| Unanswerable questions correctly refused | 92.0% |
| Retrieval: a gold page in the top 5 | 76.1% |
| Citation precision (share of citations on a gold page) | 0.06 |
| Answers citing at least one gold page | 10.3% |
| Latency p50 / p95 | 6.04 s / 8.17 s |
| Time to first token, p50 | 6.04 s |
| LLM calls per question | 3 |
| Cost per question | $0.000274 |
| Errors | 0 |

| Question type | Questions | Correct | False refusals | Retrieval hit@5 | Citation precision |
| --- | --- | --- | --- | --- | --- |
| change_percent | 14 | 0.0% | 100.0% | 71.4% | 0.0 |
| list | 6 | 16.7% | 50.0% | 83.3% | 0.196 |
| lookup_number | 97 | 12.4% | 82.5% | 76.3% | 0.06 |
| unanswerable | 25 | 92.0% | n/a | n/a | n/a |

| Document class | Questions | Correct | Retrieval hit@5 |
| --- | --- | --- | --- |
| A_annual_report | 42 | 16.7% | 65.7% |
| B_scanned | 35 | 22.9% | 72.4% |
| C_mixed_technical | 21 | 33.3% | 82.4% |
| D_table_heavy | 30 | 33.3% | 80.0% |
| E_amharic_scanned | 14 | 28.6% | 100.0% |

## How to reproduce

```
python -m evaluation.run extract --run runs/<name>
python -m evaluation.run qa --run runs/<name>
python -m evaluation.run score --run runs/<name>
```

Scores are deterministic (no LLM judge). Golden figures marked `draft` have not yet been confirmed by a person.
