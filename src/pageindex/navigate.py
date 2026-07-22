"""
PageIndex navigation: given a topic, return the top-K most relevant sections.

This is the cheap first hop of retrieval -- "which chapters should I open?" --
before semantic search digs into individual LDUs. Scoring is deliberately
simple and offline-safe (token overlap over title + summary + data types) so
demos work without an API key. A later step can swap in embedding similarity
without changing the tool signature.
"""

from __future__ import annotations

import re

from src.models.page_index import PageIndex, SectionNode

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text) if len(t) > 2}


def score_section(topic: str, node: SectionNode) -> float:
    """Relevance score in [0, 1+] of a section for a free-text topic."""
    topic_toks = _tokens(topic)
    if not topic_toks:
        return 0.0

    title_toks = _tokens(node.title)
    summary_toks = _tokens(node.summary)
    type_toks = _tokens(" ".join(node.data_types_present))
    path_toks = _tokens(" ".join(node.path))

    # Title matches weigh most; summary next; path/types as light boosts.
    title_hits = len(topic_toks & title_toks)
    summary_hits = len(topic_toks & summary_toks)
    path_hits = len(topic_toks & path_toks)
    type_hits = len(topic_toks & type_toks)

    score = (
        3.0 * title_hits
        + 1.5 * summary_hits
        + 1.0 * path_hits
        + 0.5 * type_hits
    ) / max(len(topic_toks), 1)

    # Prefer sections that actually hold content (have chunk ids).
    if node.chunk_ids:
        score += 0.05
    return score


def navigate(
    index: PageIndex, topic: str, *, top_k: int = 3
) -> list[tuple[SectionNode, float]]:
    """Return the top-K sections for ``topic``, highest score first.

    Empty topic ? empty list. Ties break by shorter path (more specific) then
    earlier page_start.
    """
    topic = (topic or "").strip()
    if not topic:
        return []

    scored: list[tuple[SectionNode, float]] = []
    for node in index.iter_nodes():
        s = score_section(topic, node)
        if s > 0:
            scored.append((node, s))

    scored.sort(
        key=lambda item: (-item[1], len(item[0].path), item[0].page_start)
    )
    return scored[:top_k]
