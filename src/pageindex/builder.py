"""
PageIndex builder: turn Phase 3 LDUs into a navigable section tree.

Analogy: after the bookbinder (chunker) cuts the scroll into index cards, this
module shelves those cards under chapter tabs and writes a one-paragraph blurb
on each tab -- so a librarian can point you to the right chapter without
reading every card.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path

from src.chunking.models import DocumentChunk
from src.config import CHUNKS_DIR, PAGEINDEX_DIR
from src.models.page_index import PageIndex, SectionNode

logger = logging.getLogger("docmind.pageindex")

# Sentinel: "try the factory"; explicit ``None`` means offline/extractive only.
_AUTO = object()

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_SUMMARY_MAX_CHARS = 400
_SNIPPET_FOR_LLM = 1200


def load_chunks_jsonl(path: Path | str) -> list[DocumentChunk]:
    """Load LDUs written by the Phase 3 pipeline (one JSON object per line)."""
    chunks: list[DocumentChunk] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                chunks.append(DocumentChunk.model_validate_json(line))
    return chunks


def _extractive_summary(texts: list[str], max_chars: int = _SUMMARY_MAX_CHARS) -> str:
    """Offline fallback: first 1-2 sentences from the section's body text."""
    joined = " ".join(t.strip() for t in texts if t.strip())
    if not joined:
        return ""
    sentences = [s for s in _SENTENCE_SPLIT.split(joined) if s]
    summary = " ".join(sentences[:2]).strip()
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "..."
    return summary


def _llm_summary(title: str, texts: list[str], client) -> str | None:
    """Ask a cheap text model for a 2-3 sentence section blurb. None on failure."""
    body = " ".join(texts)[:_SNIPPET_FOR_LLM]
    if not body.strip():
        return None
    prompt = (
        "Summarize this document section in 2-3 factual sentences. "
        "No preamble. No bullet points.\n\n"
        f"Section title: {title}\n\n"
        f"Section text:\n{body}"
    )
    try:
        result = client.complete(prompt, temperature=0.0, max_tokens=150)
        text = (result.text or "").strip()
        return text or None
    except Exception as exc:  # pragma: no cover - network/provider
        logger.warning("PageIndex LLM summary failed for %r: %s", title, exc)
        return None


def _aggregate_sections(
    chunks: list[DocumentChunk],
) -> dict[tuple[str, ...], dict]:
    """Group chunks by exact parent_hierarchy path and collect page/type stats."""
    buckets: dict[tuple[str, ...], dict] = defaultdict(
        lambda: {
            "pages": set(),
            "types": set(),
            "chunk_ids": [],
            "texts": [],
        }
    )
    for chunk in chunks:
        path = tuple(chunk.metadata.parent_hierarchy)
        if not path:
            path = ("(untitled)",)
        bucket = buckets[path]
        bucket["pages"].update(chunk.metadata.page_numbers)
        bucket["types"].add(chunk.metadata.chunk_type)
        bucket["chunk_ids"].append(chunk.id)
        bucket["texts"].append(chunk.text)
    return buckets


def _build_tree(
    buckets: dict[tuple[str, ...], dict],
    summaries: dict[tuple[str, ...], str],
) -> list[SectionNode]:
    """Assemble nested SectionNodes from flat path->stats buckets."""
    # Ensure every ancestor path exists so orphans don't float.
    all_paths = set(buckets.keys())
    for path in list(buckets.keys()):
        for depth in range(1, len(path)):
            all_paths.add(path[:depth])

    def make_node(path: tuple[str, ...]) -> SectionNode:
        data = buckets.get(path)
        child_paths = sorted(
            p for p in all_paths if len(p) == len(path) + 1 and p[: len(path)] == path
        )
        children = [make_node(p) for p in child_paths]

        if data:
            pages = sorted(data["pages"]) or [1]
            page_start, page_end = pages[0], pages[-1]
            # Expand span to include descendants.
            for child in children:
                page_start = min(page_start, child.page_start)
                page_end = max(page_end, child.page_end)
            return SectionNode(
                title=path[-1],
                page_start=page_start,
                page_end=page_end,
                path=list(path),
                summary=summaries.get(path, ""),
                data_types_present=sorted(data["types"]),
                chunk_ids=list(data["chunk_ids"]),
                children=children,
            )

        # Ancestor-only node (no direct chunks): inherit span from children.
        if children:
            page_start = min(c.page_start for c in children)
            page_end = max(c.page_end for c in children)
        else:
            page_start = page_end = 1
        return SectionNode(
            title=path[-1],
            page_start=page_start,
            page_end=page_end,
            path=list(path),
            summary=summaries.get(path, ""),
            children=children,
        )

    root_paths = sorted(p for p in all_paths if len(p) == 1)
    return [make_node(p) for p in root_paths]


def build_page_index(
    chunks: list[DocumentChunk],
    *,
    doc_id: str,
    source_filename: str = "",
    summarize: bool = True,
    llm_client=_AUTO,
) -> PageIndex:
    """Build a PageIndex from LDUs.

    Args:
        chunks: Phase 3 DocumentChunks.
        doc_id: stable document id (matches profile / chunk filename stem).
        source_filename: original PDF name for display.
        summarize: if True, attach per-section summaries.
        llm_client: text LLM client, ``None`` for extractive-only (offline),
            or omit to auto-resolve via ``get_text_client()``.
    """
    buckets = _aggregate_sections(chunks)
    summaries: dict[tuple[str, ...], str] = {}

    if summarize:
        client = llm_client
        if client is _AUTO:
            try:
                from src.llm.factory import get_text_client

                client = get_text_client()
            except Exception:  # pragma: no cover
                client = None

        for path, data in buckets.items():
            title = path[-1]
            if client is not None:
                llm_text = _llm_summary(title, data["texts"], client)
                if llm_text:
                    summaries[path] = llm_text
                    continue
            summaries[path] = _extractive_summary(data["texts"])

    roots = _build_tree(buckets, summaries)
    return PageIndex(doc_id=doc_id, source_filename=source_filename, roots=roots)


def save_page_index(index: PageIndex, directory: Path | None = None) -> Path:
    """Persist PageIndex JSON under ``.refinery/pageindex/{doc_id}.json``."""
    out_dir = directory or PAGEINDEX_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{index.doc_id}.json"
    path.write_text(index.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_page_index(doc_id: str, directory: Path | None = None) -> PageIndex:
    """Load a previously saved PageIndex."""
    path = (directory or PAGEINDEX_DIR) / f"{doc_id}.json"
    return PageIndex.model_validate_json(path.read_text(encoding="utf-8"))


def build_and_save_from_chunks_file(
    doc_id: str,
    *,
    chunks_dir: Path | None = None,
    source_filename: str = "",
    summarize: bool = True,
    llm_client=_AUTO,
) -> tuple[PageIndex, Path]:
    """Convenience: load ``{doc_id}.jsonl`` chunks, build, and save PageIndex."""
    chunks_path = (chunks_dir or CHUNKS_DIR) / f"{doc_id}.jsonl"
    chunks = load_chunks_jsonl(chunks_path)
    index = build_page_index(
        chunks,
        doc_id=doc_id,
        source_filename=source_filename,
        summarize=summarize,
        llm_client=llm_client,
    )
    path = save_page_index(index)
    return index, path
