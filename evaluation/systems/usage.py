"""Count LLM calls, tokens, cost and time without changing the system under test.

The provider client classes are wrapped at runtime, so every call made by any
part of the pipeline (triage, vision extraction, planner, answer writer) is
recorded in a ``UsageMeter``.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Call:
    kind: str  # "llm" | "embed"
    seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    label: str = ""


@dataclass
class UsageMeter:
    calls: list[Call] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, call: Call) -> None:
        with self._lock:
            self.calls.append(call)

    def reset(self) -> None:
        with self._lock:
            self.calls.clear()

    def summary(self) -> dict:
        llm = [c for c in self.calls if c.kind == "llm"]
        emb = [c for c in self.calls if c.kind == "embed"]
        return {
            "llm_calls": len(llm),
            "llm_seconds": round(sum(c.seconds for c in llm), 3),
            "input_tokens": sum(c.input_tokens for c in llm),
            "output_tokens": sum(c.output_tokens for c in llm),
            "llm_cost_usd": round(sum(c.cost_usd for c in llm), 6),
            "embed_calls": len(emb),
            "embed_seconds": round(sum(c.seconds for c in emb), 3),
            "embed_tokens_est": sum(c.input_tokens for c in emb),
            "embed_cost_usd": round(sum(c.cost_usd for c in emb), 6),
            "total_cost_usd": round(sum(c.cost_usd for c in self.calls), 6),
        }


METER = UsageMeter()
_installed = False

EMBED_PRICE_PER_M = 0.02  # text-embedding-3-small list price, USD per 1M tokens


def install() -> UsageMeter:
    """Wrap the V1 provider clients once per process."""
    global _installed
    if _installed:
        return METER
    from src.llm.providers._openai_compatible import OpenAICompatibleClient
    from src.retrieval.embeddings import OpenAIEmbeddingClient

    original_chat = OpenAICompatibleClient.chat

    def chat(self, messages, **kwargs):
        start = time.perf_counter()
        result = original_chat(self, messages, **kwargs)
        system = next((m.get("content") for m in messages if m.get("role") == "system"), "")
        METER.add(
            Call(
                kind="llm",
                seconds=time.perf_counter() - start,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                label=str(system)[:40] if isinstance(system, str) else "vision",
            )
        )
        return result

    original_embed = OpenAIEmbeddingClient.embed

    def embed(self, texts):
        start = time.perf_counter()
        out = original_embed(self, texts)
        tokens = sum(len(t) for t in texts) // 4
        METER.add(
            Call(
                kind="embed",
                seconds=time.perf_counter() - start,
                input_tokens=tokens,
                cost_usd=tokens / 1e6 * EMBED_PRICE_PER_M,
            )
        )
        return out

    OpenAICompatibleClient.chat = chat
    OpenAIEmbeddingClient.embed = embed
    _installed = True
    return METER


@contextmanager
def measured():
    """Yield a dict filled with the usage of the calls made inside the block."""
    before = len(METER.calls)
    box: dict = {}
    start = time.perf_counter()
    try:
        yield box
    finally:
        box["seconds"] = time.perf_counter() - start
        inner = UsageMeter(calls=METER.calls[before:])
        box.update(inner.summary())
