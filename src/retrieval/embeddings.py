"""
OpenAI embedding client for Phase 4 vector retrieval.

Turns LDU text into dense vectors via the OpenAI Embeddings API
(``text-embedding-3-small`` by default). Batches requests for cost/latency and
reuses the shared HTTP retry helper.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from src.config import EmbeddingConfig, VisionConfig
from src.llm._http import post_json

logger = logging.getLogger("docmind.embeddings")

_OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


class EmbeddingClient(ABC):
    """Provider-agnostic embedder: texts in, vectors out."""

    model: str = "base"

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed one or more texts; returns one vector per input, same order."""
        raise NotImplementedError


class OpenAIEmbeddingClient(EmbeddingClient):
    """OpenAI ``/v1/embeddings`` client (supports Matryoshka ``dimensions``)."""

    provider = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
    ):
        key = api_key if api_key is not None else VisionConfig.OPENAI_API_KEY
        if not key:
            raise ValueError(
                "OPENAI_API_KEY is required for OpenAI embeddings. "
                "Set it in .env or pass api_key=..."
            )
        self._api_key = key
        self.model = model or EmbeddingConfig.MODEL
        self.dimensions = (
            dimensions if dimensions is not None else EmbeddingConfig.DIMENSIONS
        )
        self.batch_size = batch_size or EmbeddingConfig.BATCH_SIZE

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # OpenAI rejects empty strings; keep positional alignment with placeholders.
        cleaned = [t if t.strip() else " " for t in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(cleaned), self.batch_size):
            batch = cleaned[start : start + self.batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        payload: dict = {"model": self.model, "input": texts}
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions
        data = post_json(
            _OPENAI_EMBEDDINGS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        # API may return items out of order; sort by index.
        items = sorted(data["data"], key=lambda row: row["index"])
        return [item["embedding"] for item in items]


def build_embedding_client() -> EmbeddingClient:
    """Factory: currently OpenAI-only (per Phase 4 product choice)."""
    provider = (EmbeddingConfig.PROVIDER or "openai").lower()
    if provider != "openai":
        raise ValueError(
            f"Unsupported embedding provider '{provider}'. "
            "Only 'openai' is configured in this build."
        )
    return OpenAIEmbeddingClient()
