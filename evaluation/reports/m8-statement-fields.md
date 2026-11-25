# M8: financial statement fields

Schema `financial_statement_summary` v1, 20 labelled documents. Generated 2026-11-25T07:57:56+00:00. Extractor as for invoices; pages chosen by statement (title near the top and the statement's row labels), the company's own statements preferred over the group's, a business-line row moved to its Total column when the parts add up, scale read from the page header, entity names by agreement across pages. Set: 20 annual reports and audited statements (Commercial Bank of Ethiopia, Development Bank, Ethio Telecom, Ethiopian Reinsurance, EthSwitch); answers drafted with gpt-4.1-mini from the statement pages, every value checked against the page text, 5 documents corrected against the page images (draft until a person confirms them).

| Metric | Value |
| --- | --- |
| Field F1 (micro, all fields and line items) | **97.5%** |
| Precision / recall | 97.5% / 97.5% |
| Values accepted without review | 95.6% |
| ...of which right | 99.4% |
| Wrong values sent to review | 75.0% (4 wrong values) |
| Right values read from the answer's page | 85.4% |
| Time per document, p50 | 8.36 s |
| Cost per document | $0.004206 |
| Documents that failed | 0 |

| Field | Right | Wrong or extra | Missed | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| entity_name | 19 | 1 | 1 | 95.0% | 95.0% | 95.0% |
| period_end | 20 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| currency | 20 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| total_assets | 20 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| total_liabilities | 20 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| total_equity | 20 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| profit_before_tax | 19 | 1 | 1 | 95.0% | 95.0% | 95.0% |
| profit_after_tax | 18 | 2 | 2 | 90.0% | 90.0% | 90.0% |

**What was wrong**

| Document | Field | Extracted | Answer | Review? |
| --- | --- | --- | --- | --- |
| audited_fs_2019 | profit_before_tax | (3,880,965) | 10553638000.0 | yes |
| audited_fs_2020 | entity_name | ees | Ethio Telecom | yes |
| audited_fs_2020 | profit_after_tax | :433:072 | 9453072000.0 | yes |
| ethiore_2022 | profit_after_tax | 233,523,541 | 223523541.0 | no |
