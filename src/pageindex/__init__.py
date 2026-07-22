"""PageIndex: hierarchical navigation over document sections.

    from src.pageindex import build_page_index, navigate, save_page_index
"""

from src.pageindex.builder import (
    build_and_save_from_chunks_file,
    build_page_index,
    load_chunks_jsonl,
    load_page_index,
    save_page_index,
)
from src.pageindex.navigate import navigate, score_section

__all__ = [
    "build_page_index",
    "build_and_save_from_chunks_file",
    "load_chunks_jsonl",
    "load_page_index",
    "save_page_index",
    "navigate",
    "score_section",
]
