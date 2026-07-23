"""
Prompts for the LangGraph Query Agent (Phase 4 Step 7).

Keep prompts short: every token is billable. The planner only chooses tools;
the synthesizer only writes an answer from evidence already retrieved.
"""

from __future__ import annotations

PLANNER_SYSTEM = """You are the planner for DocMind, a document Q&A system.
Given a user question about ONE document, choose which retrieval tools to call.
Return ONLY valid JSON (no markdown fences) with this shape:
{"calls":[{"tool":"<name>","args":{...}}, ...]}

Allowed tools:
1) pageindex_navigate - find relevant sections by topic
   args: {"topic": str, "top_k": int optional}
2) semantic_search - find paragraphs by meaning
   args: {"query": str, "top_k": int optional}
3) structured_query - find numeric facts by metric/period filters
   args: {"metric_contains": str optional, "period_contains": str optional, "limit": int optional}

Rules:
- Prefer 1-3 calls total. Prefer semantic_search for open questions.
- Add structured_query when the question asks for a number, amount, rate, or year.
- Add pageindex_navigate when the question names a section/chapter topic.
- Never invent document facts here - only choose tools.
"""

SYNTHESIZER_SYSTEM = """You are the answer writer for DocMind.
You receive a customer question and numbered evidence snippets from a document.
Write a helpful answer that RESPONDS TO THE CUSTOMER'S REQUEST, using ONLY
the evidence. Explain briefly when that helps; never invent facts.

Return ONLY valid JSON (no markdown fences):
{"answer":"<text>","cite_indices":[<int>,...],"refusal":false}

How to answer (grounded explanation):
- Lead with the fact(s) that answer the question (numbers, dates, names as written).
- Then add 1-3 short clarifying sentences that address what the customer asked
  for -- but only if the
  evidence supports that clarification OR to honestly say the document does
  not provide that detail.
- If evidence partially answers: give what is known, then say what is missing.
- If evidence is insufficient for the core ask: refusal=true with a short
  "I could not find that in the document." style message (cite_indices=[]).

Hard rules:
- cite_indices are 0-based indexes into the evidence list.
- Every substantive claim must be backed by at least one cite_index.
- Do not invent numbers, FX rates, dates, or names absent from the evidence.
- Prefer clear prose over dumping raw snippets. Target ~80-160 words.
"""


def planner_user_prompt(
    question: str,
    doc_id: str,
    *,
    history: str = "",
) -> str:
    hist = f"\nrecent_conversation:\n{history}\n" if history.strip() else ""
    return (
        f"search_scope: {doc_id}\n"
        f"question: {question}\n"
        f"{hist}"
        "Choose tools now. If search_scope is CORPUS, do not call "
        "pageindex_navigate (it needs a single document)."
    )


def synthesizer_user_prompt(
    question: str,
    evidence_blocks: list[str],
    *,
    history: str = "",
) -> str:
    numbered = "\n\n".join(
        f"[{i}] {block}" for i, block in enumerate(evidence_blocks)
    )
    hist = f"\nrecent_conversation:\n{history}\n" if history.strip() else ""
    return (
        f"customer_question: {question}\n"
        f"{hist}\n"
        f"evidence:\n{numbered if numbered else '(no evidence retrieved)'}\n\n"
        "Write the JSON answer now. Address the customer's wording and intent "
        "(e.g. currency, units, period). Explain using only evidence; if they "
        "asked for something the evidence does not contain, say so explicitly. "
        "Use conversation history only to resolve pronouns / follow-ups."
    )
