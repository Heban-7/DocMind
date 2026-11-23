"""Hand-entered golden figures and questions for golden set v1.

These cover what the text-layer drafter cannot: scanned pages (read by eye
from rendered page images), Amharic scans, and figures stated in prose.
Every entry names its page; ``source`` says how it was read. All start as
``draft`` until a person confirms them against the page.

Run ``python -m evaluation.draft.manual_v1`` to write manual_figures.json and
manual_questions.json next to the golden set.
"""

from __future__ import annotations

import json

from evaluation.schema import GoldFigure, GoldQuestion, GoldSource, QuestionType, golden_dir

V = GoldSource.VISUAL
T = GoldSource.TEXT_LAYER
K = 1e3
M = 1e6
B = 1e9

FIGURES: list[GoldFigure] = []
QUESTIONS: list[GoldQuestion] = []


def fig(fid, doc, page, label, col, text, value, scale=1.0, unit="ETB", period="", source=V, note="", table=""):
    FIGURES.append(
        GoldFigure(
            figure_id=fid, doc_key=doc, page=page, row_label=label, column_label=col,
            value_text=text, value=value, scale=scale, unit=unit, period=period,
            source=source, review_note=note, table_title=table,
        )
    )
    return FIGURES[-1]


def lookup(qid, f: GoldFigure, question, answer=""):
    QUESTIONS.append(
        GoldQuestion(
            question_id=qid, doc_key=f.doc_key, question=question, qtype=QuestionType.LOOKUP_NUMBER,
            gold_value=f.absolute_value, gold_value_raw=f.value, gold_is_percent=f.unit == "%",
            gold_pages=[f.page], figure_ids=[f.figure_id],
            gold_answer_text=answer or f"{f.value_text}{' ' + f.unit if f.unit and f.unit != '%' else ''}",
        )
    )


def change(qid, doc, old: GoldFigure, new: GoldFigure, question):
    pct = (new.value - old.value) / abs(old.value) * 100
    QUESTIONS.append(
        GoldQuestion(
            question_id=qid, doc_key=doc, question=question, qtype=QuestionType.CHANGE_PERCENT,
            gold_value=round(pct, 2), gold_value_raw=round(pct, 2), gold_is_percent=True, tolerance=0.02,
            gold_pages=sorted({old.page, new.page}), figure_ids=[old.figure_id, new.figure_id],
            gold_answer_text=f"{pct:+.1f}% ({old.value_text} to {new.value_text})",
        )
    )


def listq(qid, doc, question, items, pages):
    QUESTIONS.append(
        GoldQuestion(
            question_id=qid, doc_key=doc, question=question, qtype=QuestionType.LIST,
            gold_items=items, gold_pages=pages, gold_answer_text="; ".join(items),
        )
    )


def unanswerable(qid, doc, question):
    QUESTIONS.append(
        GoldQuestion(
            question_id=qid, doc_key=doc, question=question, qtype=QuestionType.UNANSWERABLE,
            gold_answer_text="The document does not contain this; the system should say so.",
        )
    )


# --- Ethio Telecom IFRS financial statements FY ended 30 June 2021 (scanned) ---
d = "audited_fs_2021"
rev21 = fig("audited_fs_2021-m01", d, 1, "Revenue from contracts with customers", "30 June 2021", "55,499,196", 55499196, K, period="FY ended 30 June 2021", note="Birr'000", table="Statement of profit or loss")
rev20 = fig("audited_fs_2021-m02", d, 1, "Revenue from contracts with customers", "30 June 2020", "47,628,412", 47628412, K, period="FY ended 30 June 2020", note="Birr'000", table="Statement of profit or loss")
pat21 = fig("audited_fs_2021-m03", d, 1, "Profit / (loss) after tax", "30 June 2021", "5,583,227", 5583227, K, period="FY ended 30 June 2021", note="Birr'000")
pat20 = fig("audited_fs_2021-m04", d, 1, "Profit / (loss) after tax", "30 June 2020", "9,453,072", 9453072, K, period="FY ended 30 June 2020", note="Birr'000")
fin21 = fig("audited_fs_2021-m05", d, 1, "Finance costs", "30 June 2021", "(10,191,041)", -10191041, K, period="FY ended 30 June 2021", note="Birr'000; OCR misreads this as (20,191,041)")
ta21 = fig("audited_fs_2021-m06", d, 2, "Total assets", "30 June 2021", "77,218,285", 77218285, K, period="30 June 2021", note="Birr'000", table="Statement of financial position")
te20 = fig("audited_fs_2021-m07", d, 2, "Total equity", "30 June 2020", "11,527,708", 11527708, K, period="30 June 2020", note="Birr'000")
re21 = fig("audited_fs_2021-m08", d, 2, "Retained earnings", "30 June 2021", "(4,790,941)", -4790941, K, period="30 June 2021", note="Birr'000")
lookup("audited_fs_2021-q01", rev21, "In Ethio Telecom's IFRS financial statements for the year ended 30 June 2021, what was revenue from contracts with customers for that year?", "Birr 55,499,196 thousand (about Birr 55.5 billion)")
lookup("audited_fs_2021-q02", fin21, "What were Ethio Telecom's finance costs for the year ended 30 June 2021?", "Birr (10,191,041) thousand")
lookup("audited_fs_2021-q03", ta21, "What were Ethio Telecom's total assets at 30 June 2021?", "Birr 77,218,285 thousand")
lookup("audited_fs_2021-q04", re21, "What were Ethio Telecom's retained earnings at 30 June 2021?", "Birr (4,790,941) thousand, a deficit")
change("audited_fs_2021-q05", d, pat20, pat21, "By what percentage did Ethio Telecom's profit after tax change from the year ended 30 June 2020 to the year ended 30 June 2021?")
unanswerable("audited_fs_2021-q06", d, "How many mobile subscribers did Ethio Telecom report at 30 June 2021 in these financial statements?")
_ = (rev20, te20)

# --- Development Bank of Ethiopia audit report 2023 (scanned) ---
d = "dbe_audit_2023"
debt23 = fig("dbe_audit_2023-m01", d, 15, "Proceeds from issue of debt securities", "Bank 30 June 2023", "15,854,181", 15854181, K, period="FY ended 30 June 2023", note="Birr'000; Bank column", table="Statement of cash flows")
debt22 = fig("dbe_audit_2023-m02", d, 15, "Proceeds from issue of debt securities", "Bank 30 June 2022", "11,277,399", 11277399, K, period="FY ended 30 June 2022", note="Birr'000; Bank column")
cash23 = fig("dbe_audit_2023-m03", d, 15, "Cash and cash equivalents at the end of the year", "Bank 30 June 2023", "33,087,090", 33087090, K, period="30 June 2023", note="Birr'000; Bank column")
int23 = fig("dbe_audit_2023-m04", d, 15, "Interest received", "Bank 30 June 2023", "7,031,415", 7031415, K, period="FY ended 30 June 2023", note="Birr'000")
pbt23 = fig("dbe_audit_2023-m05", d, 66, "Profit/(Loss) before tax", "Bank 30 June 2023", "6,463,494", 6463494, K, period="FY ended 30 June 2023", note="Birr'000; note 13b", table="13b Reconciliation of effective tax to statutory tax")
pbt22 = fig("dbe_audit_2023-m06", d, 66, "Profit/(Loss) before tax", "Bank 30 June 2022", "3,426,199", 3426199, K, period="FY ended 30 June 2022", note="Birr'000")
tax23 = fig("dbe_audit_2023-m07", d, 66, "Total income tax expense/(income)", "Bank 30 June 2023", "725,496", 725496, K, period="FY ended 30 June 2023", note="Birr'000")
lookup("dbe_audit_2023-q01", debt23, "According to the Development Bank of Ethiopia's cash flow statement, how much did the Bank receive from issuing debt securities in the year ended 30 June 2023?")
lookup("dbe_audit_2023-q02", cash23, "What were the Development Bank of Ethiopia's (Bank, not Group) cash and cash equivalents at the end of the year ended 30 June 2023?")
lookup("dbe_audit_2023-q03", tax23, "What was the Development Bank of Ethiopia's total income tax expense for the year ended 30 June 2023?")
change("dbe_audit_2023-q04", d, pbt22, pbt23, "By what percentage did the Development Bank of Ethiopia's profit before tax change from the year ended 30 June 2022 to the year ended 30 June 2023?")
lookup("dbe_audit_2023-q05", int23, "How much interest did the Development Bank of Ethiopia receive in the year ended 30 June 2023?")
unanswerable("dbe_audit_2023-q06", d, "What was the Development Bank of Ethiopia's profit before tax for the year ended 30 June 2030?")
_ = debt22

# --- CBE Annual Report 2010-11 (scanned) ---
d = "cbe_2010_11"
exp11 = fig("cbe_2010_11-m01", d, 12, "Total expenses of the Bank", "2010/11", "2,756", 2756, M, period="2010/11", note="prose: 'reached Birr 2,756 million'")
expinc = fig("cbe_2010_11-m02", d, 12, "Increase in total expenses over the preceding year", "2010/11", "63.5%", 63.5, unit="%", period="2010/11")
recr = fig("cbe_2010_11-m03", d, 20, "Permanent employees recruited", "2010/11", "2,473", 2473, unit="employees", period="2010/11")
staff = fig("cbe_2010_11-m04", d, 20, "Staff strength at end of the fiscal year", "2010/11", "10,753", 10753, unit="employees", period="2010/11")
trained = fig("cbe_2010_11-m05", d, 20, "Employees offered training programs", "2010/11", "9,705", 9705, unit="employees", period="2010/11")
lookup("cbe_2010_11-q01", exp11, "According to the CBE Annual Report 2010-11, what were the Bank's total expenses in the fiscal year under review?", "Birr 2,756 million")
lookup("cbe_2010_11-q02", staff, "What was CBE's staff strength at the end of the 2010/11 fiscal year?")
lookup("cbe_2010_11-q03", recr, "How many permanent employees did CBE recruit during 2010/11?")
lookup("cbe_2010_11-q04", expinc, "By what percentage did CBE's total expenses increase in 2010/11 compared with the preceding year?")
lookup("cbe_2010_11-q05", trained, "How many CBE employees were offered training programs in 2010/11?")
unanswerable("cbe_2010_11-q06", d, "How many ATMs did CBE operate in Kenya according to the 2010-11 annual report?")

# --- CBE Annual Report 2009-10 (scanned) ---
d = "cbe_2009_10"
e09 = fig("cbe_2009_10-m01", d, 11, "Total expenses of the Bank", "2008/09", "1,132", 1132, M, period="2008/09", note="prose")
e10 = fig("cbe_2009_10-m02", d, 11, "Total expenses of the Bank", "2009/10", "1,676", 1676, M, period="2009/10", note="prose")
hr = fig("cbe_2009_10-m03", d, 16, "Human resources of the Bank at end of fiscal year", "2009/10", "8,726", 8726, unit="employees", period="2009/10")
newemp = fig("cbe_2009_10-m04", d, 16, "New employees recruited", "2009/10", "1,209", 1209, unit="employees", period="2009/10")
cap = fig("cbe_2009_10-m05", d, 29, "Capital of the Bank (increased to)", "30 June 2007", "4,000,000,000", 4_000_000_000, period="year ended 30 June 2007", note="note 20 Capital")
lookup("cbe_2009_10-q01", e10, "According to the CBE Annual Report 2009-10, what were the Bank's total expenses in 2009/10?", "Birr 1,676 million")
lookup("cbe_2009_10-q02", hr, "How many employees did CBE have at the end of fiscal year 2009/10?")
lookup("cbe_2009_10-q03", newemp, "How many new employees did CBE recruit in 2009/10?")
change("cbe_2009_10-q04", d, e09, e10, "By what percentage did CBE's total expenses grow from 2008/09 to 2009/10?")
lookup("cbe_2009_10-q05", cap, "To what amount was the capital of the Bank increased, according to note 20 of the CBE 2009-10 annual report?")
unanswerable("cbe_2009_10-q06", d, "What was CBE's mobile banking revenue in 2009/10?")

# --- EthSwitch Annual Report 2019 (scanned) ---
d = "ethswitch_2019"
tx = fig("ethswitch_2019-m01", d, 9, "Interbank transactions processed", "fiscal year", "27,062,074", 27062074, unit="transactions")
txprev = fig("ethswitch_2019-m02", d, 9, "Interbank transactions, previous fiscal year", "previous fiscal year", "23,031,552", 23031552, unit="transactions")
wd = fig("ethswitch_2019-m03", d, 9, "Successful cash withdrawals", "fiscal year", "15,044,699", 15044699, unit="transactions")
ta = fig("ethswitch_2019-m04", d, 25, "Total assets", "fiscal year", "272,937,443.00", 272937443.0)
pbt20 = fig("ethswitch_2019-m05", d, 37, "Profit before tax", "2020", "28,015,111", 28015111, period="2020", table="Statement of cash flows")
pbt19 = fig("ethswitch_2019-m06", d, 37, "Profit before tax", "2019", "13,658,388", 13658388, period="2019")
lookup("ethswitch_2019-q01", tx, "How many interbank transactions did EthSwitch process in the fiscal year covered by its 2019 annual report?")
lookup("ethswitch_2019-q02", wd, "How many successful cash withdrawals were among EthSwitch's interbank transactions that year?")
lookup("ethswitch_2019-q03", ta, "What did EthSwitch's total assets rise to during the fiscal year under review in the 2019 annual report?")
change("ethswitch_2019-q04", d, pbt19, pbt20, "By what percentage did EthSwitch's profit before tax change from 2019 to 2020, according to the cash flow statement?")
change("ethswitch_2019-q05", d, txprev, tx, "By what percentage did EthSwitch's interbank transaction volume grow compared with the previous fiscal year?")
unanswerable("ethswitch_2019-q06", d, "How many mobile wallets were linked to EthSwitch in 2019 according to this report?")

# --- Security Vulnerability Disclosure Standard Procedure (scanned, text) ---
d = "security_disclosure"
wd120 = fig("security_disclosure-m01", d, 11, "Minimum time to allow before disclosure", "", "120", 120, unit="working days", note="'at least 120 working days'")
ack = fig("security_disclosure-m02", d, 13, "Acknowledgement of a report", "", "5", 5, unit="business days", note="'within 5 business days'")
tls = fig("security_disclosure-m03", d, 6, "Minimum recommended TLS version", "", "1.2", 1.2, unit="version", note="'minimum version recommended to be used is TLS1.2'")
lookup("security_disclosure-q01", wd120, "Under the Security Vulnerability Disclosure Standard Procedure, at least how many working days should a reporter allow before public disclosure?", "At least 120 working days")
lookup("security_disclosure-q02", ack, "Within how many business days will receipt of a vulnerability report be acknowledged?", "5 business days")
lookup("security_disclosure-q03", tls, "What is the minimum TLS version recommended in the Security Vulnerability Disclosure Standard Procedure?", "TLS 1.2")
listq("security_disclosure-q04", d, "According to the Security Vulnerability Disclosure Standard Procedure, which kinds of vulnerabilities are out of scope?",
      ["Volumetric vulnerabilities", "headers", "TLS1.0 support"], [9])
unanswerable("security_disclosure-q05", d, "What cash reward does the procedure pay for a critical vulnerability?")

# --- Amharic scans ---
d = "am_budget"
tb13 = fig("am_budget-m01", d, 1, "Total approved budget (programs 1-4)", "Budget year 2013 approved budget", "97,447", 97447, K, period="2013 E.C.", note="(በሺህ ብር) thousands of birr", table="Annex 1.4")
te12 = fig("am_budget-m02", d, 1, "Total expense (programs 1-4)", "Budget year 2012 expense", "50,401", 50401, K, period="2012 E.C.")
p2b = fig("am_budget-m03", d, 1, "Program 2: Investment promotion (ኢንቨስትመንትን መሳብ) approved budget", "Budget year 2013 approved budget", "14,963", 14963, K, period="2013 E.C.")
p1q3 = fig("am_budget-m04", d, 1, "Program 1: Management and administration, expense up to Q3", "2013 expense to Q3", "18,100", 18100, K, period="2013 E.C. Q1-Q3")
tb12 = fig("am_budget-m05", d, 1, "Total approved budget (programs 1-4)", "Budget year 2012 approved budget", "82,358", 82358, K, period="2012 E.C.")
lookup("am_budget-q01", tb13, "In the 2013 E.C. regular budget and expense document, what was the total approved budget for budget year 2013?", "97,447 thousand birr")
lookup("am_budget-q02", te12, "What was the total expense in budget year 2012 according to the 2013 E.C. budget and expense document?", "50,401 thousand birr")
lookup("am_budget-q03", p2b, "What approved budget did Program 2 (investment promotion) receive for 2013 E.C.?", "14,963 thousand birr")
change("am_budget-q04", d, tb12, tb13, "By what percentage did the total approved budget change from budget year 2012 to budget year 2013?")
lookup("am_budget-q05", p1q3, "How much had Program 1 (management and administration) spent up to the third quarter of 2013 E.C.?", "18,100 thousand birr")
unanswerable("am_budget-q06", d, "What was the approved capital budget for 2014 E.C.?")

d = "am_procurement"
pr1 = fig("am_procurement-m01", d, 1, "Contract price, single-source procurement of investment licence security printing", "", "640,780.00", 640780.0, note="ጠቅላላ ዋጋ")
pr2 = fig("am_procurement-m02", d, 1, "Contract price, restricted tender for hotel services", "", "482,228.46", 482228.46, note="V1's vision output read this as 382,228.46")
pr3 = fig("am_procurement-m03", d, 1, "Contract price, open tender 006/2011 for garage services", "", "375,400.00", 375400.0)
lookup("am_procurement-q01", pr1, "In the 2013 E.C. procurement information document, what was the total contract price of the single-source procurement?", "640,780.00 birr")
lookup("am_procurement-q02", pr2, "What was the total contract price for the hotel service procured by restricted tender?", "482,228.46 birr")
lookup("am_procurement-q03", pr3, "What was the total contract price for the garage service procured under open tender 006/2011?", "375,400.00 birr")
listq("am_procurement-q04", d, "Which procurement methods appear in the 2013 E.C. procurement information document?",
      ["single source", "restricted tender", "open tender"], [1])
unanswerable("am_procurement-q05", d, "What was the contract price for vehicle procurement in this document?")

d = "am_audit_findings"
yr = fig("am_audit_findings-m01", d, 1, "Audited budget year", "", "2011", 2011, unit="year", note="ኦዲት የተደረገው የበጀት ዓመት")
lookup("am_audit_findings-q01", yr, "Which budget year was audited, according to the 2013 E.C. audit finding information document?", "2011 E.C.")
listq("am_audit_findings-q02", d, "Which institution was audited in the 2013 E.C. audit finding information document?", ["Ethiopian Investment Commission"], [1])
unanswerable("am_audit_findings-q03", d, "What total amount of money did the auditors recover in this document?")

# --- Prose figures in digital documents ---
d = "pharma_2019"
g = fig("pharma_2019-m01", d, 4, "Average economic growth over the past 10 years", "", "9.68%", 9.68, unit="%", source=T)
pop = fig("pharma_2019-m02", d, 9, "Ethiopia's share of Africa's population", "", "~8.5%", 8.5, unit="%", source=T)
lookup("pharma_2019-q01", g, "According to the Pharmaceutical Manufacturing Opportunities in Ethiopia report, what was Ethiopia's average economic growth over the past 10 years?")
lookup("pharma_2019-q02", pop, "What share of Africa's population does the pharmaceutical report attribute to Ethiopia?")
unanswerable("pharma_2019-q03", d, "What was the total value of pharmaceutical exports from Ethiopia in 2030?")

d = "ethswitch_10th_2023_24"
p2p = fig("ethswitch_10th-m01", d, 11, "Person-to-Person (P2P) interoperable transactions", "2023/24", "14,140,881", 14140881, unit="transactions", source=T)
assets = fig("ethswitch_10th-m02", d, 12, "Increase in total assets", "2023/24", "64%", 64, unit="%", source=T)
pbt = fig("ethswitch_10th-m03", d, 12, "Increase in net profit before tax", "2023/24", "172%", 172, unit="%", source=T)
cards = fig("ethswitch_10th-m04", d, 18, "Personalized cards delivered", "2023/24", "380,795", 380795, unit="cards", source=T)
lookup("ethswitch_10th-q01", p2p, "How many P2P interoperable transactions did EthSwitch process in 2023/24, according to its 10th annual report?")
lookup("ethswitch_10th-q02", assets, "By what percentage did EthSwitch's total assets increase in 2023/24?")
lookup("ethswitch_10th-q03", pbt, "By what percentage did EthSwitch's net profit before tax increase in 2023/24?")
lookup("ethswitch_10th-q04", cards, "How many personalized cards did EthSwitch deliver to member banks in 2023/24?")

d = "ethiore_2019"
gwp = fig("ethiore_2019-m01", d, 9, "Gross written premiums of the insurance industry (30 June 2017)", "30 June 2017", "7.4", 7.4, B, period="30 June 2017", source=T, note="prose; two-column page")
lookup("ethiore_2019-q01", gwp, "According to the Ethiopian Reinsurance annual report (June 2019 file), what did the gross written premiums of the insurance industry reach as at 30 June 2017?", "Birr 7.4 billion")

# --- CPI bulletins (prose and Table 1) ---
for doc, month, yoy, prev, mom, food, nonfood, p2_page in [
    ("cpi_2025_08", "August", 13.6, 17.2, 1.1, 12.7, 15.1, 2),
    ("cpi_2025_03", "March", 13.6, 26.2, 2.7, 11.9, 16.2, 2),
    ("cpi_2025_06", "June", 13.9, 19.9, 0.5, 11.7, 17.3, 2),
]:
    f1 = fig(f"{doc}-m01", doc, 1, f"Year-on-year general inflation, {month} EFY2017", "", f"{yoy}", yoy, unit="%", period=f"{month} EFY2017", source=T)
    f2 = fig(f"{doc}-m02", doc, 1, f"Year-on-year general inflation, {month} EFY2016", "", f"{prev}", prev, unit="%", period=f"{month} EFY2016", source=T)
    f3 = fig(f"{doc}-m03", doc, 1, f"Month-on-month general inflation, {month} EFY2017", "", f"{mom}", mom, unit="%", period=f"{month} EFY2017", source=T)
    f4 = fig(f"{doc}-m04", doc, p2_page, f"Food inflation (year-on-year), {month} EFY2017", "Food", f"{food}", food, unit="%", period=f"{month} EFY2017", source=T, table="Table 1")
    f5 = fig(f"{doc}-m05", doc, p2_page, f"Non-food inflation (year-on-year), {month} EFY2017", "Non-Food", f"{nonfood}", nonfood, unit="%", period=f"{month} EFY2017", source=T, table="Table 1")
    lookup(f"{doc}-q01", f1, f"What was the year-on-year general inflation rate for {month} EFY2017 in the CPI bulletin?")
    lookup(f"{doc}-q02", f2, f"According to the {month} EFY2017 CPI bulletin, what was the year-on-year general inflation rate a year earlier, in {month} EFY2016?")
    lookup(f"{doc}-q03", f3, f"What was the month-on-month general inflation rate in {month} EFY2017?")
    lookup(f"{doc}-q04", f4, f"What was year-on-year food inflation in {month} EFY2017?")
    lookup(f"{doc}-q05", f5, f"What was year-on-year non-food inflation in {month} EFY2017?")
    unanswerable(f"{doc}-q06", doc, f"What was the year-on-year inflation rate for Kenya in {month} EFY2017 according to this bulletin?")


def main() -> None:
    root = golden_dir("v1")
    (root / "manual_figures.json").write_text(
        json.dumps([f.model_dump(mode="json") for f in FIGURES], indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (root / "manual_questions.json").write_text(
        json.dumps([q.model_dump(mode="json") for q in QUESTIONS], indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(FIGURES)} manual figures, {len(QUESTIONS)} manual questions")


if __name__ == "__main__":
    main()
