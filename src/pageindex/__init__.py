"""PageIndex: hierarchical navigation over document sections.

    from src.pageindex import build_page_index, navigate
"""

from src.pageindex.builder import (
    build_page_index,
    load_chunks_jsonl,
)
from src.pageindex.navigate import navigate, score_section

__all__ = [
    "build_page_index",
    "load_chunks_jsonl",
    "navigate",
    "score_section",
]
