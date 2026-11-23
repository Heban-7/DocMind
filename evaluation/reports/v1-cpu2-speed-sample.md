# V1 CPU 2-thread speed sample

Golden set v1: 25 documents, 1237 pages, 184 figures, 142 questions (0 figures confirmed by a person so far).
Generated 2026-11-23T07:08:20+00:00 on Intel64 Family 6 Model 186 Stepping 2, GenuineIntel; V1 extraction on CPU only, 2 threads (DOCMIND_DEVICE=cpu DOCMIND_NUM_THREADS=2) on an x86 laptop, to approximate the 2-core server; ARM cores are expected to be slower

## Extraction

| Metric | Value |
| --- | --- |
| Pages with extracted content | 56 of 57 (98.2%) |
| Pages silently missing (no content, no failure flag) | 1 |
| Gold figures intact on the right page | 100.0% |
| Gold figures with digits split by spaces | 0.0% |
| Gold figures missing from the whole extraction | 0.0% |
| Gold figures found only on another page | 0.0% |
| Label and value on the same row (table row integrity) | 92.6% |
| FactTable holds the right value | 77.8% |
| FactTable holds the figure with a wrong value | 7.4% |
| Ingest time, all documents | 386.8 s |
| Ingest API cost, all documents | $0.0006 |

**By document class**

| Class | Figures | Intact on page | Split digits | Missing | Row intact | Fact correct |
| --- | --- | --- | --- | --- | --- | --- |
| A_annual_report | 10 | 100.0% | 0.0% | 0.0% | 100.0% | 100.0% |
| C_mixed_technical | 12 | 100.0% | 0.0% | 0.0% | 100.0% | 66.7% |
| D_table_heavy | 5 | 100.0% | 0.0% | 0.0% | 60.0% | 60.0% |

**Speed by engine** (extraction stage, per page that produced content)

| Engine | Documents | Pages | Seconds per page | Device |
| --- | --- | --- | --- | --- |
| layout_docling | 3 | 57 | 6.5 | cpu |

**Per document**

| Document | Class | Pages | Engine | Content pages | Silently missing | Extract s | s per extracted page | Facts | Cost $ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cbe_2023_24 | | | not run | | | | | | |
| ethiore_2017 | | | not run | | | | | | |
| ets_2023_24 | | | not run | | | | | | |
| ethswitch_10th_2023_24 | | | not run | | | | | | |
| ethswitch_2021_22 | | | not run | | | | | | |
| cbe_2006_07 | | | not run | | | | | | |
| ethiore_profile_2024_25 | A | 24 | layout_docling | 23 | 1 | 146.2 | 6.36 | 12 | 0.0002 |
| dbe_audit_2023 | | | not run | | | | | | |
| cbe_2010_11 | | | not run | | | | | | |
| cbe_2009_10 | | | not run | | | | | | |
| ethswitch_2019 | | | not run | | | | | | |
| audited_fs_2021 | | | not run | | | | | | |
| security_disclosure | | | not run | | | | | | |
| fta_survey_2022 | | | not run | | | | | | |
| pharma_2019 | | | not run | | | | | | |
| ethiore_2019 | | | not run | | | | | | |
| cbe_2012_13 | C | 20 | layout_docling | 20 | 0 | 123.6 | 6.18 | 160 | 0.0002 |
| tax_exp_2021_22 | | | not run | | | | | | |
| tax_exp_sample | | | not run | | | | | | |
| cpi_2025_08 | D | 13 | layout_docling | 13 | 0 | 94.2 | 7.25 | 166 | 0.0002 |
| cpi_2025_03 | | | not run | | | | | | |
| cpi_2025_06 | | | not run | | | | | | |
| am_audit_findings | | | not run | | | | | | |
| am_procurement | | | not run | | | | | | |
| am_budget | | | not run | | | | | | |

## How to reproduce

```
python -m evaluation.run extract --system v1 --run runs/<name>
python -m evaluation.run qa --system v1 --run runs/<name>
python -m evaluation.run score --run runs/<name>
```

Scores are deterministic (no LLM judge). Golden figures marked `draft` have not yet been confirmed by a person.
