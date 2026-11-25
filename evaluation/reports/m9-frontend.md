# M9: the web app shows its evidence

Before M9 a citation in the web app was a badge reading "[Verified]" that opened
the whole PDF in an iframe, with the box printed as four numbers and nothing
drawn. The upload modal moved its progress bar on a timer, the contact form said
"Inquiry sent successfully!" and sent nothing, and the schema fields of M8 had no
screen at all.

## Citation boxes (benchmark)

Same golden set and answer engine as M7 (gpt-4o-mini, 142 questions), rerun with
the M9 citation code. Full report: [m9-citation-boxes.md](m9-citation-boxes.md).

| Measure | M7 | M9 |
| --- | --- | --- |
| Citations with a box smaller than the page | 87 of 180 (48%), cells of facts only; the app drew none | 179 of 180 (99.4%) |
| Right answers whose box covers the printed gold figure (45 with a gold box) | 39 (86.7%) | 44 (97.8%) |
| Median box, share of the page area | whole page | 0.07% |
| Citation support (on a page that prints the answer; target 90%) | 0.866 | **0.900** |
| Citation precision (on the gold page) | 0.618 | 0.653 |
| Questions answered right | 85.2% | 85.2% |
| Unanswerable questions refused | 96% | 96% |
| Time added by checking and boxing (p50 / p95) | | 0.05 s / 0.89 s |
| Cost per question | $0.00056 | $0.00056 |

How a citation is boxed, best first (`src/query/locate.py`):

1. the table cell a fact was read from (both cells for a change between two years);
2. the cell that prints the figure the answer states, with its row label, found in
   the document model saved beside the PDF; when the same figure is printed under a
   business line and under Total, the Total;
3. the text block that prints a figure in running text;
4. the blocks the passage came from;
5. the page, said in words ("This citation points at the whole page").

A passage that runs over two pages moves its citation to the page that prints the
figure, which is where the precision and support gains come from. Every citation
is boxed on its own document's file (an answer over two documents used the first
document's PDF for both).

Time to first token was 1.6 s in this run against 1.1 s for M7. Nothing in M9 runs
before the first token; the difference is the network on the day: OpenAI calls
took longer (model p50 2.10 s against 1.85 s, query embedding 0.75 s against
0.34 s), and 17 of the 142 questions timed out on the first pass and were rerun.

## What changed in the app

- **PDF viewer** (react-pdf, client only): the cited page opens with the boxes
  drawn; turning pages renders from the PDF already loaded. The PDF is fetched
  with the sign-in header; the sign-in token is no longer accepted in a URL.
  "Open in a new tab" asks for a ten-minute link to that one document.
- **Fields**: a page per document to read a schema's fields, see each value's box
  on its page, and confirm, correct or reject it; the schema's checks; CSV and
  Excel export. A review page lists every value waiting for a person.
- **How each page was read**: the extraction ledger per page (engine, confidence,
  time, cost, flags), from `GET /documents/{id}/ledger`.
- **Model menu**: per provider, the price per 1M tokens and the date it was
  checked, the cost of a typical answer (measured on the golden set, or from the
  price), the golden-set score, badges (Default, Best score, Fastest, Free tier
  with data use), and why a model is locked (Add a key to enable, Budget reached).
- **Answer footer**: model, time, tokens and cost, with the split by stage
  (reading the question, finding evidence, writing, checking) and by kind of call.
- **Usage page**: spend against the account and server caps, by day, provider,
  model and kind of call, the average cost per question, and each document's
  reading and field costs.
- **Benchmark page**: the milestones' scores, compiled from these reports by
  `python -m evaluation.export_benchmarks`.
- **Removed**: the fake contact form (now a link to GitHub issues), the
  "[Verified]" and "Zero-Trust Grounded Evidence" labels, the timer-driven upload
  modal, the thumbs and retry buttons that did nothing, fixed "settings" text, and
  claims the code no longer backs (SQLite, ChromaDB, triage tiers, "eliminating
  hallucinations").
- **Accessibility**: dialogs move focus in, keep Tab inside, close on Escape and
  return focus; buttons that show only an icon have labels; toggles report their
  state.
- **Errors**: a stream that ends without an answer, or a server that cannot be
  reached, says so. A question's embedding that hangs gives up after 12 s and
  search continues on keywords (one hung call used to use up the answer's whole
  60 s), and an answer stream that stalls partway is asked again without
  streaming.
- **CI**: the frontend lint step blocks again (the old lint errors are fixed),
  and a step warns when the model prices are more than 90 days old.

## Checked in the browser

On the production build, with a new account on the dev server and the 32-page
Ethiopian Reinsurance report: an answer's citation opened page 9 with the
"Gross Premium" label and its Total cell boxed; Escape closed it and returned
focus. The page ledger, the field extraction (8 fields, 3 sent to review), the
box of a field, confirming and correcting, the review queue, the Excel export
(200, 6 KB) and the usage page all worked.
