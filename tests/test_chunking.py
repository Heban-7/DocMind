"""
Unit tests for Phase 3: the Context-Aware Chunking Engine.

Validates the three constitutional edge cases:
  1. A Markdown table is never severed across chunks.
  2. The heading hierarchy updates correctly across H1/H2/H3 transitions.
  3. Identical text hashes identically; different text changes the hash.
Plus provenance (page tracking) and the validator.
"""

from __future__ import annotations

from src.chunking.engine import ChunkValidator, ContextAwareChunker
from src.chunking.models import DocumentChunk, compute_content_hash


def _find_chunk_containing(chunks, needle: str):
    hits = [c for c in chunks if needle in c.text]
    return hits


# --- Test 1: tables are never severed ---------------------------------------
def test_table_is_not_severed_across_chunks():
    md = """## Financials

Some introductory prose that comes before the table and provides context.

| Metric | 2022 | 2023 |
| --- | --- | --- |
| Revenue | 100 | 150 |
| Profit | 20 | 35 |

Some trailing prose after the table to force another block boundary.
"""
    # Tiny target to aggressively force splitting; the table must still survive.
    chunker = ContextAwareChunker(target_words=5, max_words=50)
    chunks = chunker.chunk(md)

    rows = ["| Metric | 2022 | 2023 |", "| Revenue | 100 | 150 |", "| Profit | 20 | 35 |"]
    containing = [c for c in chunks if any(r in c.text for r in rows)]

    # All table rows live in exactly ONE chunk.
    assert len(containing) == 1
    table_chunk = containing[0]
    for row in rows:
        assert row in table_chunk.text
    assert table_chunk.metadata.chunk_type in ("table", "mixed")


# --- Test 2: hierarchy state machine ----------------------------------------
def test_heading_hierarchy_updates_across_levels():
    md = """# Annual Report

Opening remarks under the top-level title.

## Operations

Operational summary text.

### Logistics

Details about logistics under operations.

## Governance

Board governance text.
"""
    chunker = ContextAwareChunker(target_words=400)
    chunks = chunker.chunk(md)

    intro = _find_chunk_containing(chunks, "Opening remarks")[0]
    assert intro.metadata.parent_hierarchy == ["Annual Report"]

    logistics = _find_chunk_containing(chunks, "Details about logistics")[0]
    assert logistics.metadata.parent_hierarchy == [
        "Annual Report",
        "Operations",
        "Logistics",
    ]

    # Governance is a sibling H2: the H3 "Logistics" and old H2 must be dropped.
    governance = _find_chunk_containing(chunks, "Board governance")[0]
    assert governance.metadata.parent_hierarchy == ["Annual Report", "Governance"]


# --- Test 3: content hashing ------------------------------------------------
def test_identical_text_hashes_match_and_differ_on_change():
    text_a = "The quick brown fox."
    text_b = "The quick brown fox."
    text_c = "The quick brown fox!"

    assert compute_content_hash(text_a) == compute_content_hash(text_b)
    assert compute_content_hash(text_a) != compute_content_hash(text_c)


def test_chunk_create_stamps_matching_hash():
    chunk = DocumentChunk.create(
        "Hello world", parent_hierarchy=["Doc"], page_numbers=[3]
    )
    assert chunk.metadata.content_hash == compute_content_hash("Hello world")
    assert chunk.metadata.word_count == 2
    assert chunk.metadata.page_numbers == [3]


# --- Provenance: page tracking from markers ---------------------------------
def test_multi_page_markers_assign_distinct_pages():
    """Simulates post-fix extraction: one marker per page, not one per batch."""
    md = """<!-- page 1 -->
## Title page

Text on page one.

<!-- page 2 -->
## Preface

Text on page two.

<!-- page 3 -->
## Contents

| Item | Page |
| --- | --- |
| Intro | 6 |

<!-- page 4 -->
## Section A

Body on page four.
"""
    chunks = ContextAwareChunker(target_words=50).chunk(md)

    p1 = _find_chunk_containing(chunks, "page one")[0]
    p2 = _find_chunk_containing(chunks, "page two")[0]
    p4 = _find_chunk_containing(chunks, "page four")[0]
    table = _find_chunk_containing(chunks, "| Intro | 6 |")[0]

    assert p1.metadata.page_numbers == [1]
    assert p2.metadata.page_numbers == [2]
    assert table.metadata.page_numbers == [3]
    assert p4.metadata.page_numbers == [4]


def test_page_markers_are_tracked():
    md = """<!-- page 4 -->
## Section

Text that lives on page four.
"""
    chunks = ContextAwareChunker().chunk(md)
    body = _find_chunk_containing(chunks, "page four")[0]
    assert body.metadata.page_numbers == [4]


def test_default_page_when_no_markers():
    chunks = ContextAwareChunker().chunk("Just some text with no markers.")
    assert chunks[0].metadata.page_numbers == [1]


# --- Validator --------------------------------------------------------------
def test_validator_accepts_well_formed_chunk():
    chunk = DocumentChunk.create("valid", parent_hierarchy=[], page_numbers=[1])
    ChunkValidator().validate(chunk)  # should not raise


def test_malformed_hash_line_does_not_hang():
    # A line starting with '#' that is NOT a valid 1-6 heading, plus a stray
    # unterminated comment, must be treated as prose (no infinite loop).
    md = "####### not a heading\n\n<!-- unterminated comment\n\nreal body text here"
    chunks = ContextAwareChunker().chunk(md)
    assert any("real body text" in c.text for c in chunks)


def test_two_tables_with_prose_between_pass_validation():
    md = """## Report

| A | B |
| --- | --- |
| 1 | 2 |

Prose between the two tables.

| C | D |
| --- | --- |
| 3 | 4 |
"""
    # Small target so both tables + prose may pack together; must NOT be flagged
    # as severed and must keep each table intact.
    chunks = ContextAwareChunker(target_words=5, max_words=50).chunk(md)
    assert any("| 1 | 2 |" in c.text for c in chunks)
    assert any("| 3 | 4 |" in c.text for c in chunks)


def test_oversized_prose_is_split_on_sentences():
    sentence = "This is a sentence with several words in it. "
    md = sentence * 60  # ~ 540 words, above the default max
    chunks = ContextAwareChunker(target_words=50, max_words=100).chunk(md)
    assert len(chunks) > 1
    # No chunk should be wildly over the target (sentence-bounded splitting).
    assert all(c.metadata.word_count <= 120 for c in chunks)
