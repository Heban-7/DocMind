# M7: answer engine v2 (one call, streamed, verified)

Golden set v1: 25 documents, 1237 pages, 184 figures, 142 questions (0 figures confirmed by a person so far).
Generated 2026-11-24T19:44:23+00:00 on Intel64 Family 6 Model 186 Stepping 2, GenuineIntel; M7: answer engine v2 on gpt-4o-mini. Rule-based plan for a first question about one document (no model call), hybrid search, fact lookup and section index in parallel, ONE streamed answer call citing evidence ids, then the verifier (numbers checked against the cited evidence, citations re-pointed, no padding, names and years the evidence never mentions mean not found). Prompt profile answer-v2.0, mode balanced. Extraction and index reused from the M6 run (unchanged). 6 of 142 questions hit a network outage on the test machine in the first attempts and were rerun; the published run had 0 errors. Run-to-run variation at temperature 0 was about 2 points (83.1% and 85.2% for the last two runs of near-identical code).

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
| Questions answered correctly | 85.2% of 142 |
| Answerable questions answered correctly | 82.9% |
| False refusals on answerable questions | 6.0% |
| Unanswerable questions correctly refused | 96.0% |
| Retrieval: a gold page in the top 5 | 82.9% |
| Citation precision (share of citations on a gold page) | 0.618 |
| Citation support (share of citations on a page that prints the answer) | 0.866 |
| Answers citing at least one gold page | 70.1% |
| "Not found" answers that still state the right figure | 6 |
| Latency p50 / p95 | 2.35 s / 3.47 s |
| Time to first token, p50 | 1.1 s |
| LLM calls per question | 1 |
| Cost per question | $0.00056 |
| Errors | 0 |

| Question type | Questions | Correct | False refusals | Retrieval hit@5 | Citation precision |
| --- | --- | --- | --- | --- | --- |
| change_percent | 14 | 71.4% | 14.3% | 78.6% | 0.602 |
| list | 6 | 50.0% | 33.3% | 83.3% | 0.417 |
| lookup_number | 97 | 86.6% | 3.1% | 83.5% | 0.632 |
| unanswerable | 25 | 96.0% | n/a | n/a | n/a |

| Document class | Questions | Correct | Retrieval hit@5 |
| --- | --- | --- | --- |
| A_annual_report | 42 | 85.7% | 85.7% |
| B_scanned | 35 | 80.0% | 79.3% |
| C_mixed_technical | 21 | 90.5% | 88.2% |
| D_table_heavy | 30 | 96.7% | 72.0% |
| E_amharic_scanned | 14 | 64.3% | 100.0% |

## M6 -> M7, and the two choices M7 made

Same golden set, same extraction and index (reused from the M6 run). The M6 column was rescored with the M7 scorer, which adds the citation-support and "not found but correct" rows.

| Metric | M6 (3 calls, gpt-4o-mini) | **M7** (rule plan, gpt-4o-mini) | M7, one-call LLM planner | M7 on gpt-6-luna |
| --- | --- | --- | --- | --- |
| Questions answered correctly | 76.8% | **85.2%** | 81.7% | 83.8% |
| Answerable questions correct | 78.6% | **82.9%** | 79.5% | 81.2% |
| False refusals (answerable) | 0.0% | **6.0%** | 5.1% | 6.0% |
| Unanswerable questions refused | 68.0% | **96.0%** | 92.0% | 96.0% |
| Citation precision (citations on the gold page) | 0.233 | **0.618** | 0.544 | 0.684 |
| Citation support (citations on a page that prints the answer) | 0.365 | **0.866** | 0.789 | 0.874 |
| "Not found" answers that still state the right figure | 0 | **6** | 6 | 3 |
| Time to first token, p50 | 10.6 s | **1.1 s** | 3.06 s | 1.29 s |
| Answer time, p50 | 10.6 s | **2.35 s** | 4.28 s | 1.89 s |
| Answer time, p95 | 15.05 s | **3.47 s** | 5.73 s | 2.77 s |
| Model calls per question | 3 | **1** | 2 | 1 |
| Cost per question (USD) | 0.000872 | **0.00056** | 0.000672 | 0.000379 |

| Question type | M6 | **M7** | M7, LLM planner | M7 on gpt-6-luna |
| --- | --- | --- | --- | --- |
| change_percent | 85.7% | **71.4%** | 64.3% | 71.4% |
| list | 66.7% | **50.0%** | 50.0% | 33.3% |
| lookup_number | 78.4% | **86.6%** | 83.5% | 85.6% |
| unanswerable | 68.0% | **96.0%** | 92.0% | 96.0% |

**Targets from the plan.** Correctness >= 85%: met (85.2%; run-to-run variation is about 2 points). Time to first token <= 2 s: met (1.1 s p50 on a link that adds about 0.8 s per round trip to the provider). Citation precision >= 90%: not met (0.62 on the gold page, 0.87 on a page that prints the answer; M6 0.23 / 0.37).

**Planner.** The rule-based plan (no model call) beat the one-call LLM planner on every measure: 85.2% vs 81.7% correct, first token 1.1 s vs 3.1 s, cost $0.00056 vs $0.00067. The LLM planner stays for follow-up questions (it resolves "it" and "that year" from the conversation) and for questions across several documents (it picks the document).

**Model.** gpt-6-luna answered 83.8% correctly at $0.00038 per question (32% cheaper, first token 1.3 s). gpt-4o-mini stays the default; gpt-6-luna is in the picker as the cheaper option. Both results are in rubric/models.yaml and served by GET /models.

**Where it is still wrong (21 of 142).** Lists fell from 4 of 6 to 3 of 6 (two "Table 4.2" / "Table 3" questions where the table's chunk is not retrieved). Percent-change fell from 12 of 14 to 10 of 14: an OCR'd statement whose year headers read "30June2023" matches a subsidiary's column (extraction, not the answer step), and two changes where no table row matched, so the model gave both figures but no change. Six answers still say "Not found" while stating the right figure (label wording, Amharic tables). The OCR'd Ethio Telecom statement still shifts labels by a row (extraction).

How the M7 numbers were made: `DOCMIND_EVAL_ACCOUNT=eval-m6 python -m evaluation.run qa --run runs/m7` with runs/m7 holding copies of runs/m6/extraction and runs/m6/refinery; `DOCMIND_PLANNER=llm` for the planner run and `--model gpt-6-luna` for the model run.

## How to reproduce

```
python -m evaluation.run extract --run runs/<name>
python -m evaluation.run qa --run runs/<name>
python -m evaluation.run score --run runs/<name>
```

Scores are deterministic (no LLM judge). Golden figures marked `draft` have not yet been confirmed by a person.
