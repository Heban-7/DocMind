"""
Intent router -- the Librarian for multi-document search (STEP 2).

Reads the user's question + a catalog of available documents, then decides:
  * a specific document_id (search that shelf only), or
  * None (federated / corpus-wide search).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.agents.json_util import extract_json
from src.config import PROFILES_DIR
from src.llm.base import LLMClient
from src.models.intent import CorpusDocument, IntentRouter, SearchScope

logger = logging.getLogger("docmind.intent_router")

ROUTER_SYSTEM = """You are the document librarian for DocMind.
Given a user question and a catalog of available documents, decide whether to
search ONE specific document or the ENTIRE corpus.

Return ONLY valid JSON (no markdown fences):
{"document_id":"<id or null>","confidence":0.0,"rationale":"<short reason>"}

Rules:
- If the question clearly names or uniquely matches one catalog entry
  (filename, doc id, domain), set document_id to that id.
- If the question is general, compares documents, or does not identify one
  document, set document_id to null (corpus-wide search).
- document_id MUST be either null or an id that appears in the catalog.
- Prefer corpus-wide when unsure.
"""


def list_corpus_documents(profiles_dir: Path | None = None) -> list[CorpusDocument]:
    """Build a catalog from saved triage profiles under ``.refinery/profiles``."""
    root = profiles_dir or PROFILES_DIR
    if not root.exists():
        return []
    docs: list[CorpusDocument] = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        doc_id = str(data.get("doc_id") or path.stem).strip()
        if not doc_id:
            continue
        docs.append(
            CorpusDocument(
                document_id=doc_id,
                document_name=str(data.get("source_filename") or ""),
                domain_hint=str(data.get("domain_hint") or ""),
                page_count=(
                    int(data["page_count"])
                    if data.get("page_count") is not None
                    else None
                ),
            )
        )
    return docs


def _catalog_block(docs: list[CorpusDocument]) -> str:
    if not docs:
        return "(no documents indexed yet)"
    lines = []
    for d in docs:
        bits = [f"id={d.document_id}"]
        if d.document_name:
            bits.append(f"name={d.document_name}")
        if d.domain_hint:
            bits.append(f"domain={d.domain_hint}")
        if d.page_count is not None:
            bits.append(f"pages={d.page_count}")
        lines.append("- " + ", ".join(bits))
    return "\n".join(lines)


def router_user_prompt(question: str, docs: list[CorpusDocument]) -> str:
    return (
        f"question: {question}\n\n"
        f"catalog:\n{_catalog_block(docs)}\n\n"
        "Return the JSON routing decision now."
    )


def _heuristic_route(question: str, docs: list[CorpusDocument]) -> IntentRouter:
    """Offline / fallback router: match filename or doc_id substrings."""
    q = question.lower()
    matches: list[CorpusDocument] = []
    for d in docs:
        tokens = [
            d.document_id.lower(),
            d.document_name.lower(),
            Path(d.document_name).stem.lower() if d.document_name else "",
        ]
        if any(t and t in q for t in tokens if t):
            matches.append(d)
            continue
        # Loose token overlap on filename words (length >= 4).
        name_words = [
            w for w in re.findall(r"[a-z0-9]{4,}", d.document_name.lower())
            if w not in {"sample", "document", "report", "pdf"}
        ]
        if name_words and any(w in q for w in name_words):
            matches.append(d)

    if len(matches) == 1:
        d = matches[0]
        return IntentRouter(
            document_id=d.document_id,
            scope=SearchScope.SINGLE_DOCUMENT,
            confidence=0.7,
            rationale=f"Heuristic match to {d.document_name or d.document_id}.",
        )
    return IntentRouter(
        document_id=None,
        scope=SearchScope.CORPUS,
        confidence=0.6 if not matches else 0.5,
        rationale=(
            "No single document uniquely identified; searching entire corpus."
            if len(matches) != 1
            else "Multiple catalog matches; searching entire corpus."
        ),
    )


def route_intent(
    question: str,
    *,
    corpus: list[CorpusDocument] | None = None,
    llm: LLMClient | None = None,
    forced_document_id: str | None = None,
    profiles_dir: Path | None = None,
) -> IntentRouter:
    """Decide single-doc vs corpus scope for this question.

    ``forced_document_id`` (e.g. CLI ``--doc``) skips the LLM and pins scope.
    """
    docs = corpus if corpus is not None else list_corpus_documents(profiles_dir)
    known_ids = {d.document_id for d in docs}

    if forced_document_id:
        fid = forced_document_id.strip()
        return IntentRouter(
            document_id=fid,
            scope=SearchScope.SINGLE_DOCUMENT,
            confidence=1.0,
            rationale="Document scope forced by caller (--doc / deps.doc_id).",
        )

    question = (question or "").strip()
    if not question:
        return IntentRouter(
            document_id=None,
            confidence=0.0,
            rationale="Empty question; defaulting to corpus search.",
        )

    if llm is None:
        return _heuristic_route(question, docs)

    try:
        result = llm.complete(
            router_user_prompt(question, docs),
            system=ROUTER_SYSTEM,
            response_format="json",
            temperature=0.0,
            max_tokens=250,
        )
        payload = extract_json(result.text)
    except Exception as exc:  # pragma: no cover
        logger.warning("Intent router LLM failed (%s); heuristic fallback", exc)
        return _heuristic_route(question, docs)

    raw_id = payload.get("document_id", None)
    if raw_id is None or raw_id == "" or str(raw_id).lower() in {"null", "none"}:
        doc_id = None
    else:
        doc_id = str(raw_id).strip()
        if known_ids and doc_id not in known_ids:
            logger.info("Router returned unknown id %r; forcing corpus", doc_id)
            doc_id = None

    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    rationale = str(payload.get("rationale") or "").strip() or (
        "LLM routing decision."
    )

    return IntentRouter(
        document_id=doc_id,
        confidence=confidence,
        rationale=rationale,
    )
