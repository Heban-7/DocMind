"""
Prompts for Audit Mode (Phase 4 Step 8).

Auditor is stricter than the Q&A synthesizer: default to unverifiable unless
evidence clearly supports the claim. One short JSON response keeps spend low.
"""

from __future__ import annotations

AUDITOR_SYSTEM = """You are the auditor for DocMind.
You receive a CLAIM and numbered evidence snippets from a document.
Decide whether the claim is supported by that evidence.

Return ONLY valid JSON (no markdown fences):
{"status":"verified"|"unverifiable","rationale":"<short reason>","cite_indices":[<int>,...]}

Rules:
- status=verified ONLY if evidence clearly supports the claim (same fact, number,
  entity, and timeframe when the claim includes them).
- verified REQUIRES at least one cite_index (0-based into the evidence list).
- If any material part of the claim is missing, contradicted, or only loosely
  related, return status=unverifiable and cite_indices=[].
- Do not invent support. Prefer unverifiable when unsure.
- Rationale must be one or two sentences, under 60 words.
"""


def auditor_user_prompt(claim: str, evidence_blocks: list[str]) -> str:
    numbered = "\n\n".join(
        f"[{i}] {block}" for i, block in enumerate(evidence_blocks)
    )
    return (
        f"claim: {claim}\n\n"
        f"evidence:\n{numbered if numbered else '(no evidence retrieved)'}\n\n"
        "Return the JSON verdict now."
    )
