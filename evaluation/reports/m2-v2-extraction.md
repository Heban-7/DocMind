# M2: V2 extraction (page-level routing)

Golden set v1: 25 documents, 1237 pages, 184 figures, 142 questions (0 figures confirmed by a person so far).
Generated 2026-11-23T10:07:00+00:00 on Intel64 Family 6 Model 186 Stepping 2, GenuineIntel; V2 extractor (page-level routing, commit 50c7559); downstream pipeline unchanged from V1; RTX 4060 laptop GPU; TableFormer accurate mode

## Extraction

| Metric | Value |
| --- | --- |
| Pages with extracted content | 1236 of 1237 (99.9%) |
| Pages silently missing (no content, no failure flag) | 1 |
| Gold figures intact on the right page | 97.3% |
| Gold figures with digits split by spaces | 0.0% |
| Gold figures missing from the whole extraction | 2.2% |
| Gold figures found only on another page | 0.5% |
| Label and value on the same row (table row integrity) | 80.4% |
| FactTable holds the right value | 56.0% |
| FactTable holds the figure with a wrong value | 4.9% |
| Ingest time, all documents | 3319.8 s |
| Ingest API cost, all documents | $0.1899 |

**By document class**

| Class | Figures | Intact on page | Split digits | Missing | Row intact | Fact correct |
| --- | --- | --- | --- | --- | --- | --- |
| A_annual_report | 76 | 100.0% | 0.0% | 0.0% | 93.4% | 76.3% |
| B_scanned | 34 | 94.1% | 0.0% | 2.9% | 61.8% | 38.2% |
| C_mixed_technical | 26 | 100.0% | 0.0% | 0.0% | 92.3% | 73.1% |
| D_table_heavy | 39 | 100.0% | 0.0% | 0.0% | 82.1% | 28.2% |
| E_amharic_scanned | 9 | 66.7% | 0.0% | 33.3% | 0.0% | 22.2% |

**Speed by engine** (extraction stage, per page that produced content; for page-level routing, per page by the engine that read it)

| Engine | Pages | Seconds per page | p95 | Device |
| --- | --- | --- | --- | --- |
| docling | 293 | 2.16 | 3.83 | cuda |
| ocr | 398 | 4.37 | 7.72 | cuda |
| text_layer | 512 | 0.23 | 0.6 | cuda |
| vision | 34 | 11.9 | 20.44 | cuda |

Pages flagged for a person to check: 84

**Per document**

| Document | Class | Pages | Engine | Content pages | Silently missing | Extract s | s per extracted page | Facts | Cost $ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cbe_2023_24 | A | 161 | docling:100, ocr:11, text_layer:49, vision:1 | 161 | 0 | 262.8 | 1.63 | 3261 | 0.0074 |
| ethiore_2017 | A | 104 | docling:28, ocr:11, text_layer:61, vision:4 | 103 | 1 | 130.0 | 1.26 | 1099 | 0.0166 |
| ets_2023_24 | A | 92 | docling:26, ocr:11, text_layer:48, vision:7 | 92 | 0 | 249.6 | 2.71 | 601 | 0.0398 |
| ethswitch_10th_2023_24 | A | 80 | docling:5, ocr:43, text_layer:28, vision:4 | 80 | 0 | 176.1 | 2.2 | 526 | 0.0234 |
| ethswitch_2021_22 | A | 84 | docling:30, ocr:3, text_layer:49, vision:2 | 84 | 0 | 117.8 | 1.4 | 656 | 0.0121 |
| cbe_2006_07 | A | 60 | docling:33, ocr:8, text_layer:19 | 60 | 0 | 103.1 | 1.72 | 1107 | 0.0006 |
| ethiore_profile_2024_25 | A | 24 | docling:2, ocr:1, text_layer:18, vision:3 | 24 | 0 | 39.0 | 1.63 | 12 | 0.0119 |
| dbe_audit_2023 | B | 95 | ocr:93, text_layer:1, vision:1 | 95 | 0 | 533.1 | 5.61 | 3055 | 0.0074 |
| cbe_2010_11 | B | 62 | ocr:56, vision:6 | 62 | 0 | 205.1 | 3.31 | 178 | 0.0342 |
| cbe_2009_10 | B | 38 | ocr:37, vision:1 | 38 | 0 | 298.7 | 7.86 | 444 | 0.006 |
| ethswitch_2019 | B | 70 | ocr:67, vision:3 | 70 | 0 | 360.6 | 5.15 | 551 | 0.0174 |
| audited_fs_2021 | B | 3 | ocr:3 | 3 | 0 | 26.8 | 8.93 | 164 | 0.0001 |
| security_disclosure | B | 15 | ocr:15 | 15 | 0 | 59.2 | 3.94 | 1 | 0.0001 |
| fta_survey_2022 | C | 155 | docling:14, ocr:6, text_layer:135 | 155 | 0 | 112.9 | 0.73 | 468 | 0.0014 |
| pharma_2019 | C | 15 | ocr:1, text_layer:13, vision:1 | 15 | 0 | 17.7 | 1.18 | 1 | 0.0056 |
| ethiore_2019 | C | 32 | docling:2, ocr:21, text_layer:9 | 32 | 0 | 102.4 | 3.2 | 324 | 0.0003 |
| cbe_2012_13 | C | 20 | docling:8, ocr:2, text_layer:9, vision:1 | 20 | 0 | 18.5 | 0.93 | 155 | 0.0042 |
| tax_exp_2021_22 | D | 60 | docling:25, text_layer:35 | 60 | 0 | 105.2 | 1.75 | 667 | 0.0006 |
| tax_exp_sample | D | 20 | docling:6, text_layer:14 | 20 | 0 | 15.8 | 0.79 | 141 | 0.0003 |
| cpi_2025_08 | D | 13 | docling:5, text_layer:8 | 13 | 0 | 18.0 | 1.38 | 154 | 0.0002 |
| cpi_2025_03 | D | 12 | docling:4, text_layer:8 | 12 | 0 | 15.8 | 1.32 | 150 | 0.0001 |
| cpi_2025_06 | D | 13 | docling:5, text_layer:8 | 13 | 0 | 20.0 | 1.54 | 155 | 0.0002 |
| am_audit_findings | E | 3 | ocr:3 | 3 | 0 | 12.0 | 3.99 | 0 | 0.0 |
| am_procurement | E | 3 | ocr:3 | 3 | 0 | 14.1 | 4.7 | 0 | 0.0 |
| am_budget | E | 3 | ocr:3 | 3 | 0 | 17.3 | 5.77 | 43 | 0.0 |

## How to reproduce

```
python -m evaluation.run extract --system v1 --run runs/<name>
python -m evaluation.run qa --system v1 --run runs/<name>
python -m evaluation.run score --run runs/<name>
```

Scores are deterministic (no LLM judge). Golden figures marked `draft` have not yet been confirmed by a person.
