"""
The shared contract every extraction engine must obey.

`BaseExtractionEngine` is an Abstract Base Class (ABC): it cannot be used
directly, it only defines the *shape* that all real engines must fill in. By
forcing every engine to expose the same `extract(file_path) -> str` method, the
rest of the pipeline (especially the ExtractionRouter) can treat any engine
interchangeably -- it never needs to know which concrete engine it holds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseExtractionEngine(ABC):
    """Abstract interface for a document-to-markdown extraction engine."""

    #: Short human-readable name, overridden by each concrete engine.
    name: str = "base"

    @abstractmethod
    def extract(self, file_path: str) -> str:
        """Extract a document into a single unified text/markdown string.

        Every concrete engine MUST implement this. The return value is always a
        plain string so that downstream stages have one predictable input type,
        regardless of which strategy produced it.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name='{self.name}'>"
