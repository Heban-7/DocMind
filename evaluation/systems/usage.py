"""Count LLM calls, tokens, cost and time without changing the system under test.

Every call made by any part of the pipeline (vision extraction, planner,
answer writer, embeddings) reports its usage to ``src.llm.usage``; the meter
listens and records it in a ``UsageMeter``.
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
    """Listen to the usage every model and embedding call reports (once per process).

    Since M7 the LLM layer reports each call itself (streamed or not, any
    provider), so nothing is wrapped any more.
    """
    global _installed
    if _installed:
        return METER
    from src.llm import usage

    def listen(event) -> None:
        METER.add(
            Call(
                kind=event.kind,
                seconds=event.latency_ms / 1000,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                cost_usd=event.cost_usd,
                label=event.purpose,
            )
        )

    usage.add_listener(listen)
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
