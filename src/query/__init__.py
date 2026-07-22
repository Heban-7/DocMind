"""Query tools + evidence bundles for the Phase 4 agent.

    from src.query.tools import pageindex_navigate, semantic_search, structured_query
    from src.query.provenance import assemble_provenance
"""

from src.query.bbox import clear_page_size_cache, resolve_page_bbox
from src.query.evidence import EvidenceHit, ToolResult
from src.query.provenance import assemble_provenance, citation_from_hit
from src.query.tools import (
    pageindex_navigate,
    semantic_search,
    structured_query,
    tool_semantic_search,
)

__all__ = [
    "EvidenceHit",
    "ToolResult",
    "pageindex_navigate",
    "semantic_search",
    "tool_semantic_search",
    "structured_query",
    "assemble_provenance",
    "citation_from_hit",
    "resolve_page_bbox",
    "clear_page_size_cache",
]
