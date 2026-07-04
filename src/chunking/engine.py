"""
The Context-Aware Chunking Engine (Phase 3).

Turns the standardized Markdown produced by Phase 2 into a list of
`DocumentChunk` LDUs that are RAG-ready: right-sized, structurally intact, and
stamped with a heading breadcrumb, source pages, and a content hash.

------------------------------------------------------------------------------
HOW THE HEADING TRACKER WORKS (the state machine)
------------------------------------------------------------------------------
We read the Markdown top-to-bottom, one block at a time, keeping a single piece
of mutable state: a `stack` of (level, title) pairs representing the chain of
headings currently "in scope".

  * A heading of level L (``#`` = 1, ``##`` = 2, ...) first POPS every entry on
    the stack whose level is >= L (those sibling/child sections are now closed),
    then PUSHES (L, title). So ``## Section B`` after ``### Sub A1`` drops the
    H3 (and the old H2) and installs the new H2.
  * Any body block inherits a SNAPSHOT of the stack's titles as its
    ``parent_hierarchy`` -- e.g. ["Chapter 1", "Section A"].
  * Reaching a new heading also FLUSHES the current chunk buffer, so a chunk
    never straddles a section boundary (this is what prevents "structural
    collapse", where unrelated sections bleed into one blob).

------------------------------------------------------------------------------
HOW SPLITTING WORKS (layout-aware, never mid-structure)
------------------------------------------------------------------------------
The text is first parsed into whole BLOCKS (paragraphs, tables, lists, code
fences, blockquotes, headings) using Markdown boundaries -- never raw character
counts. Blocks are then packed into chunks up to a soft ``target_words`` size.
Atomic blocks (tables, code, blockquotes) are NEVER split, so a table's header
row can never be separated from its body. Only oversized prose/lists (beyond the
hard ``max_words`` window) are split, and only on sentence/line boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.config import CHUNK_MAX_WORDS, CHUNK_TARGET_WORDS
from src.chunking.models import DocumentChunk, compute_content_hash

# --- Line classifiers -------------------------------------------------------
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_PAGE_RE = re.compile(r"^<!--\s*page\s+(\d+)\s*-->$", re.IGNORECASE)
_LIST_RE = re.compile(r"^([-*+]\s+|\d+[.)]\s+)")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

_ATOMIC = {"table", "code", "blockquote"}
_SPLITTABLE = {"para", "list"}


def _is_table_line(stripped: str) -> bool:
    # Docling / GitHub-Flavored Markdown tables start each row with a pipe.
    return stripped.startswith("|")


def _is_table_separator(line: str) -> bool:
    """True for a Markdown table separator row like ``| --- | :--: |``."""
    s = line.strip()
    return s.startswith("|") and set(s) <= set("|-: ") and "-" in s


def _is_special_start(stripped: str) -> bool:
    return (
        stripped.startswith("#")
        or stripped.startswith("|")
        or stripped.startswith(">")
        or stripped.startswith("```")
        or stripped.startswith("<!--")
        or bool(_LIST_RE.match(stripped))
    )


@dataclass
class _Block:
    """A whole, indivisible-by-default Markdown unit tagged with its page."""

    kind: str
    text: str
    page: int
    level: int = 0
    title: str = ""
    words: int = field(init=False)

    def __post_init__(self) -> None:
        self.words = len(self.text.split())


def _parse_blocks(markdown: str) -> list[_Block]:
    """Tokenize Markdown into blocks, tracking the active page from markers."""
    lines = markdown.split("\n")
    blocks: list[_Block] = []
    page = 1
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        if not stripped:
            i += 1
            continue

        page_match = _PAGE_RE.match(stripped)
        if page_match:
            page = int(page_match.group(1))
            i += 1
            continue

        # Other HTML comments (e.g. <!-- image -->) carry no chunk text.
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            i += 1
            continue

        header_match = _HEADER_RE.match(stripped)
        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            blocks.append(_Block("heading", stripped, page, level, title))
            i += 1
            continue

        # Fenced code block: consume until the closing fence.
        if stripped.startswith("```"):
            buf = [raw]
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            if i < n:  # closing fence
                buf.append(lines[i])
                i += 1
            blocks.append(_Block("code", "\n".join(buf), page))
            continue

        # Table: consecutive pipe-led rows stay together (header + body).
        if _is_table_line(stripped):
            buf = []
            while i < n and _is_table_line(lines[i].strip()):
                buf.append(lines[i])
                i += 1
            blocks.append(_Block("table", "\n".join(buf), page))
            continue

        # Blockquote.
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i])
                i += 1
            blocks.append(_Block("blockquote", "\n".join(buf), page))
            continue

        # List: consecutive list items (+ indented continuations).
        if _LIST_RE.match(stripped):
            buf = []
            while i < n and lines[i].strip() and (
                _LIST_RE.match(lines[i].strip())
                or lines[i][:1] in (" ", "\t")
            ):
                buf.append(lines[i])
                i += 1
            blocks.append(_Block("list", "\n".join(buf), page))
            continue

        # Paragraph: run of plain lines until a blank or a special start.
        # Always consume the CURRENT line first (it reached here because no other
        # branch claimed it -- e.g. a malformed heading like "#####" or a stray
        # "<!--" without a closing "-->"). This guarantees forward progress and
        # prevents an infinite loop on such lines.
        buf = [raw]
        i += 1
        while i < n and lines[i].strip() and not _is_special_start(lines[i].strip()):
            buf.append(lines[i])
            i += 1
        blocks.append(_Block("para", "\n".join(buf), page))

    return blocks


def _split_oversized(block: _Block, target_words: int) -> list[_Block]:
    """Split an over-long prose/list block on natural boundaries (never mid-line
    for lists, never mid-sentence for prose)."""
    if block.kind == "list":
        units = [ln for ln in block.text.split("\n") if ln.strip()]
    else:
        units = [s for s in _SENTENCE_RE.split(block.text.strip()) if s]

    out: list[_Block] = []
    buf: list[str] = []
    count = 0
    joiner = "\n" if block.kind == "list" else " "
    for unit in units:
        w = len(unit.split())
        if buf and count + w > target_words:
            out.append(_Block(block.kind, joiner.join(buf), block.page))
            buf, count = [], 0
        buf.append(unit)
        count += w
    if buf:
        out.append(_Block(block.kind, joiner.join(buf), block.page))
    return out


class ChunkValidationError(RuntimeError):
    """Raised when an emitted chunk violates a data-quality constraint."""


class ChunkValidator:
    """Verifies each chunk obeys the constitution before it is emitted."""

    def validate(self, chunk: DocumentChunk) -> None:
        text = chunk.text
        if not text.strip():
            raise ChunkValidationError("empty chunk text")
        if chunk.metadata.content_hash != compute_content_hash(text):
            raise ChunkValidationError(
                f"content_hash mismatch for chunk {chunk.id}"
            )
        if not chunk.metadata.page_numbers:
            raise ChunkValidationError(f"chunk {chunk.id} has no page_numbers")
        # A table must never be severed from its header. Because tables are
        # parsed as atomic blocks they are never split mid-way; the one true
        # symptom of severing would be a chunk that BEGINS with a table
        # separator row (e.g. "| --- | --- |"), i.e. its header was cut off.
        non_blank = [ln for ln in text.split("\n") if ln.strip()]
        if non_blank and _is_table_separator(non_blank[0]):
            raise ChunkValidationError(
                f"table header appears severed in chunk {chunk.id}"
            )


class ContextAwareChunker:
    """Layout-aware, hierarchy-tracking Markdown chunker.

    Args:
        target_words: soft size; the packer flushes once a chunk reaches this.
        max_words: hard ceiling above which a prose/list block is sentence-split.
        validator: optional ChunkValidator run on every emitted chunk.
    """

    def __init__(
        self,
        target_words: int = CHUNK_TARGET_WORDS,
        max_words: int = CHUNK_MAX_WORDS,
        validator: ChunkValidator | None = None,
    ):
        self.target_words = target_words
        self.max_words = max_words
        self.validator = validator or ChunkValidator()

    def chunk(self, markdown: str) -> list[DocumentChunk]:
        """Convert a Markdown document into a list of validated LDUs."""
        blocks = _parse_blocks(markdown)
        chunks: list[DocumentChunk] = []
        stack: list[tuple[int, str]] = []
        buffer: list[_Block] = []

        def buffer_words() -> int:
            return sum(b.words for b in buffer)

        def flush() -> None:
            nonlocal buffer
            if not buffer:
                return
            chunks.append(self._make_chunk(buffer, [t for _, t in stack]))
            buffer = []

        for block in blocks:
            if block.kind == "heading":
                # Close the current chunk, then reshape the heading stack.
                flush()
                while stack and stack[-1][0] >= block.level:
                    stack.pop()
                stack.append((block.level, block.title))
                continue

            # Oversized prose/list: split on safe boundaries into own chunks.
            if block.kind in _SPLITTABLE and block.words > self.max_words:
                flush()
                for piece in _split_oversized(block, self.target_words):
                    chunks.append(
                        self._make_chunk([piece], [t for _, t in stack])
                    )
                continue

            # Pack: if adding this block would overflow the target, flush first
            # (this keeps atomic tables/code whole in their own chunk).
            if buffer and buffer_words() + block.words > self.target_words:
                flush()
            buffer.append(block)
            if buffer_words() >= self.target_words:
                flush()

        flush()

        for chunk in chunks:
            self.validator.validate(chunk)
        return chunks

    def _make_chunk(
        self, blocks: list[_Block], hierarchy: list[str]
    ) -> DocumentChunk:
        text = "\n\n".join(b.text.strip() for b in blocks).strip()
        pages = sorted({b.page for b in blocks}) or [1]
        kinds = {b.kind for b in blocks}
        if len(blocks) == 1:
            chunk_type = blocks[0].kind
        elif "table" in kinds:
            chunk_type = "mixed"
        else:
            chunk_type = "prose"
        return DocumentChunk.create(
            text,
            parent_hierarchy=hierarchy,
            page_numbers=pages,
            chunk_type=chunk_type,
        )
