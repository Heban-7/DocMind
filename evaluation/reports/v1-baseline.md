# V1 baseline

Golden set v1: 25 documents, 1237 pages, 184 figures, 142 questions (0 figures confirmed by a person so far).
Generated 2026-11-23T07:07:43+00:00 on Intel64 Family 6 Model 186 Stepping 2, GenuineIntel; V1 as shipped (commit 2cd9e46 code paths); extraction on an RTX 4060 laptop GPU (DOCMIND_DEVICE=auto); answers with the configured default model gpt-4o-mini (the web API default is gpt-4o); LangSmith off

## Extraction

| Metric | Value |
| --- | --- |
| Pages with extracted content | 950 of 1237 (76.8%) |
| Pages silently missing (no content, no failure flag) | 287 |
| Gold figures intact on the right page | 78.3% |
| Gold figures with digits split by spaces | 3.8% |
| Gold figures missing from the whole extraction | 15.8% |
| Gold figures found only on another page | 2.2% |
| Label and value on the same row (table row integrity) | 66.3% |
| FactTable holds the right value | 49.5% |
| FactTable holds the figure with a wrong value | 6.0% |
| Ingest time, all documents | 1609.7 s |
| Ingest API cost, all documents | $0.2249 |

**By document class**

| Class | Figures | Intact on page | Split digits | Missing | Row intact | Fact correct |
| --- | --- | --- | --- | --- | --- | --- |
| A_annual_report | 76 | 88.2% | 9.2% | 2.6% | 80.3% | 69.7% |
| B_scanned | 34 | 20.6% | 0.0% | 70.6% | 11.8% | 17.6% |
| C_mixed_technical | 26 | 100.0% | 0.0% | 0.0% | 92.3% | 65.4% |
| D_table_heavy | 39 | 100.0% | 0.0% | 0.0% | 84.6% | 35.9% |
| E_amharic_scanned | 9 | 55.6% | 0.0% | 33.3% | 0.0% | 11.1% |

**Speed by engine** (extraction stage, per page that produced content)

| Engine | Documents | Pages | Seconds per page | Device |
| --- | --- | --- | --- | --- |
| fast_text | 1 | 20 | 0.24 | cuda |
| layout_docling | 15 | 925 | 1.15 | cuda |
| vision_augmented | 9 | 292 | 9.46 | cuda |

**Per document**

| Document | Class | Pages | Engine | Content pages | Silently missing | Extract s | s per extracted page | Facts | Cost $ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cbe_2023_24 | A | 161 | layout_docling | 157 | 4 | 233.8 | 1.49 | 3249 | 0.0023 |
| ethiore_2017 | A | 104 | layout_docling | 98 | 6 | 85.7 | 0.87 | 853 | 0.0009 |
| ets_2023_24 | A | 92 | layout_docling | 88 | 4 | 142.6 | 1.62 | 680 | 0.0009 |
| ethswitch_10th_2023_24 | A | 80 | layout_docling | 80 | 0 | 99.2 | 1.24 | 60 | 0.0003 |
| ethswitch_2021_22 | A | 84 | layout_docling | 83 | 1 | 92.4 | 1.11 | 620 | 0.0012 |
| cbe_2006_07 | A | 60 | layout_docling | 60 | 0 | 90.1 | 1.5 | 1025 | 0.0008 |
| ethiore_profile_2024_25 | A | 24 | layout_docling | 23 | 1 | 16.1 | 0.7 | 12 | 0.0002 |
| dbe_audit_2023 | B | 95 | vision_augmented | 5 | 90 | 34.8 | 6.97 | 0 | 0.0284 |
| cbe_2010_11 | B | 62 | vision_augmented | 5 | 57 | 24.5 | 4.91 | 0 | 0.0281 |
| cbe_2009_10 | B | 38 | vision_augmented | 5 | 33 | 43.7 | 8.74 | 0 | 0.0282 |
| ethswitch_2019 | B | 70 | vision_augmented | 5 | 65 | 31.8 | 6.36 | 0 | 0.0282 |
| audited_fs_2021 | B | 3 | vision_augmented | 3 | 0 | 46.8 | 15.6 | 175 | 0.0182 |
| security_disclosure | B | 15 | vision_augmented | 5 | 10 | 27.9 | 5.57 | 0 | 0.0282 |
| fta_survey_2022 | C | 155 | layout_docling | 152 | 3 | 115.0 | 0.76 | 613 | 0.0024 |
| pharma_2019 | C | 15 | layout_docling | 15 | 0 | 7.7 | 0.51 | 1 | 0.0001 |
| ethiore_2019 | C | 32 | layout_docling | 19 | 13 | 31.8 | 1.67 | 26 | 0.0002 |
| cbe_2012_13 | C | 20 | layout_docling | 20 | 0 | 13.2 | 0.66 | 160 | 0.0002 |
| tax_exp_2021_22 | D | 60 | layout_docling | 60 | 0 | 61.3 | 1.02 | 1001 | 0.0009 |
| tax_exp_sample | D | 20 | fast_text | 20 | 0 | 4.8 | 0.24 | 4 | 0.0003 |
| cpi_2025_08 | D | 13 | layout_docling | 13 | 0 | 14.5 | 1.11 | 166 | 0.0002 |
| cpi_2025_03 | D | 12 | layout_docling | 12 | 0 | 12.5 | 1.04 | 164 | 0.0002 |
| cpi_2025_06 | D | 13 | layout_docling | 13 | 0 | 14.4 | 1.11 | 171 | 0.0002 |
| am_audit_findings | E | 3 | vision_augmented | 3 | 0 | 45.4 | 15.14 | 1 | 0.0179 |
| am_procurement | E | 3 | vision_augmented | 3 | 0 | 58.1 | 19.37 | 0 | 0.0187 |
| am_budget | E | 3 | vision_augmented | 3 | 0 | 37.2 | 12.39 | 63 | 0.0177 |

## Retrieval and answers

| Metric | Value |
| --- | --- |
| Questions answered correctly | 21.8% of 142 |
| Answerable questions answered correctly | 6.0% |
| False refusals on answerable questions | 85.5% |
| Unanswerable questions correctly refused | 96.0% |
| Retrieval: a gold page in the top 5 | 62.4% |
| Citation precision (share of citations on a gold page) | 0.053 |
| Answers citing at least one gold page | 7.7% |
| Latency p50 / p95 | 5.06 s / 6.64 s |
| Time to first token, p50 | 5.06 s |
| LLM calls per question | 3 |
| Cost per question | $0.000263 |
| Errors | 0 |

| Question type | Questions | Correct | False refusals | Retrieval hit@5 | Citation precision |
| --- | --- | --- | --- | --- | --- |
| change_percent | 14 | 0.0% | 100.0% | 71.4% | 0.0 |
| list | 6 | 0.0% | 50.0% | 50.0% | 0.071 |
| lookup_number | 97 | 7.2% | 85.6% | 61.9% | 0.06 |
| unanswerable | 25 | 96.0% | n/a | n/a | n/a |

| Document class | Questions | Correct | Retrieval hit@5 |
| --- | --- | --- | --- |
| A_annual_report | 42 | 16.7% | 68.6% |
| B_scanned | 35 | 17.1% | 17.2% |
| C_mixed_technical | 21 | 33.3% | 58.8% |
| D_table_heavy | 30 | 23.3% | 92.0% |
| E_amharic_scanned | 14 | 28.6% | 100.0% |

## How to reproduce

```
python -m evaluation.run extract --system v1 --run runs/<name>
python -m evaluation.run qa --system v1 --run runs/<name>
python -m evaluation.run score --run runs/<name>
```

Scores are deterministic (no LLM judge). Golden figures marked `draft` have not yet been confirmed by a person.
