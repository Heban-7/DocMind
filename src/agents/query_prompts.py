"""
Prompts for the LangGraph Query Agent (Phase 4 Step 7).

Keep prompts short: every token is billable. The planner only chooses tools;
the synthesizer only writes an answer from evidence already retrieved.
The classifier and rewriter add minimal overhead for smarter routing.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Intent Classifier — fast routing (greeting vs document query)
# ---------------------------------------------------------------------------
CLASSIFIER_SYSTEM = """You classify user intent for DocMind, a document Q&A system.
Return ONLY valid JSON (no markdown fences):
{"intent":"greeting" | "document_query"}

Rules:
- "greeting" = greetings, thanks, farewells, or pure chitchat with no document question.
- "document_query" = anything that asks about, requests info from, or relates to documents.
- When in doubt, choose "document_query" (never block a real question).
"""

# ---------------------------------------------------------------------------
# Query Rewriter — decontextualise / resolve pronouns
# ---------------------------------------------------------------------------
REWRITER_SYSTEM = """You are a query rewriter for DocMind, a document Q&A system.
Given a user's latest message and recent conversation history, produce a SINGLE
self-contained question that resolves ALL pronouns and removes conversational
fluff ("can you tell me", "I was wondering", etc.).

Return ONLY the rewritten question as plain text (no JSON, no quotes).
If the input is already a clear standalone question, return it unchanged.
Do NOT add information that was not in the original question or history.
"""

# ---------------------------------------------------------------------------
# Planner — choose retrieval tools (unchanged logic, kept for reference)
# ---------------------------------------------------------------------------
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
- Default semantic_search top_k to 7 (use 5-8). Use pageindex top_k 5 when useful.
- Add structured_query when the question asks for a number, amount, rate, or year.
- Add pageindex_navigate when the question names a section/chapter topic.
- Never invent document facts here - only choose tools.
"""

# ---------------------------------------------------------------------------
# Synthesizer — answer with provenance badges & follow-up suggestions
# ---------------------------------------------------------------------------
SYNTHESIZER_SYSTEM = """You are the answer writer for DocMind.
You receive a customer question and numbered evidence snippets from a document.
Write a helpful answer that RESPONDS TO THE CUSTOMER'S REQUEST, using ONLY
the evidence. Explain briefly when that helps; never invent facts.

Return ONLY valid JSON (no markdown fences):
{"answer":"<text>","cite_indices":[<int>,...],"refusal":false,"follow_ups":["<q1>","<q2>"]}

How to structure your "answer" text:
1. Core Answer: Lead with the fact(s) that answer the user's query (numbers, dates, names as written). Add 1-3 clarifying sentences supported by evidence.
2. Provenance Badges: After EVERY factual claim, insert an inline citation badge:
   [📄 <document_name> — Page <page_number>]
   Example: "Revenue was ETB 120.7 billion [📄 Annual_Report.pdf — Page 12]."
3. Conversational Follow-Up Paragraph (CRITICAL):
   - At the very end of your "answer" text, start a NEW PARAGRAPH (separated by a blank line).
   - In this new paragraph, conversationally suggest next topic(s) for discussion based on the retrieved information (e.g. "Would you like me to look into the revenue breakdown for FY22 next, or examine the tax exemption details in Section 4?").
   - Do NOT use bullet points, numbered lists, bold headings, or label prefixes like "Suggested Follow-ups:". Just write it naturally as a smooth closing conversational paragraph.
   - Also list the individual question string(s) in the "follow_ups" JSON array.

Formatting adaptation:
- If the customer asks to "list" something in the main answer, use bullet points for that list.
- If they ask to "compare", use a comparison format.
- For open-ended questions, use clear prose.
- Target ~80-160 words for the answer body.

Hard rules:
- cite_indices are 0-based indexes into the evidence list.
- Every substantive claim must be backed by at least one cite_index.
- For list / multi-part questions (policies, factors, findings), cite 5-7
  distinct evidence items when that many related snippets are available.
- Do not invent numbers, FX rates, dates, or names absent from the evidence.
- Evidence page refs may look like "p.8" or "PDF p.33 (document p.1)". The
  document/printed page is what readers see in the PDF; physical is the file
  sheet index. Prefer mentioning the document page when both are given.
"""


# ---- User-prompt builders ------------------------------------------------

def classifier_user_prompt(question: str) -> str:
    """Build the user prompt for intent classification."""
    return (
        f"user_message: {question}\n\n"
        "Classify the intent now. Return the JSON."
    )


def rewriter_user_prompt(
    question: str,
    *,
    history: str = "",
) -> str:
    """Build the user prompt for query rewriting / decontextualisation."""
    hist = f"\nrecent_conversation:\n{history}\n" if history.strip() else ""
    return (
        f"latest_message: {question}\n"
        f"{hist}\n"
        "Rewrite the latest message as a standalone question now."
    )


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
        "Write the JSON answer now. Format 'answer' with your evidence-backed response "
        "including [📄 Name — Page X] badges, followed by a NEW PARAGRAPH at the end "
        "that conversationally suggests next topics for discussion based on the retrieved info "
        "(no bullet points, no headers)."
    )
