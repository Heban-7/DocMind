"""Every model call reports what it used, once, to whoever listens.

Listeners are the cost ledger (API), the evaluation meter and tests. The
``purpose`` of a call ("plan", "answer", "vision", ...) and the overall
``deadline`` of the work it belongs to travel in context variables, so the
code that makes the call does not have to pass them down.

Context variables do not follow work into a thread pool on their own: submit
with ``contextvars.copy_context().run`` (see ``run_in_context``).
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

logger = logging.getLogger("docmind.llm")


@dataclass(frozen=True)
class UsageEvent:
    kind: str  # "llm" | "embed"
    provider: str
    model: str
    purpose: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    first_token_ms: float | None = None
    ok: bool = True
    error_kind: str | None = None
    streamed: bool = False


Listener = Callable[[UsageEvent], None]
_listeners: list[Listener] = []
_lock = threading.Lock()

_purpose: contextvars.ContextVar[str] = contextvars.ContextVar("docmind_llm_purpose", default="other")
_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar("docmind_llm_deadline", default=None)
_sinks: contextvars.ContextVar[tuple[list[UsageEvent], ...]] = contextvars.ContextVar("docmind_llm_sinks", default=())


def add_listener(fn: Listener) -> None:
    with _lock:
        if fn not in _listeners:
            _listeners.append(fn)


def remove_listener(fn: Listener) -> None:
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)


def emit(event: UsageEvent) -> None:
    for sink in _sinks.get():  # nested collect() blocks each get the event
        sink.append(event)
    for fn in list(_listeners):
        try:
            fn(event)
        except Exception:  # a broken listener must never fail the call
            logger.exception("usage listener failed")


def current_purpose() -> str:
    return _purpose.get()


@contextlib.contextmanager
def purpose(name: str) -> Iterator[None]:
    token = _purpose.set(name)
    try:
        yield
    finally:
        _purpose.reset(token)


def remaining_seconds() -> float | None:
    """Seconds left before the current deadline (None when there is none)."""
    d = _deadline.get()
    return None if d is None else d - time.monotonic()


@contextlib.contextmanager
def deadline(seconds: float | None) -> Iterator[None]:
    """All model calls inside the block share one time limit (the tighter one wins)."""
    if seconds is None:
        yield
        return
    new = time.monotonic() + seconds
    old = _deadline.get()
    token = _deadline.set(new if old is None else min(old, new))
    try:
        yield
    finally:
        _deadline.reset(token)


@contextlib.contextmanager
def collect() -> Iterator[list[UsageEvent]]:
    """Gather the usage of the calls made inside the block (this context only)."""
    box: list[UsageEvent] = []
    token = _sinks.set(_sinks.get() + (box,))
    try:
        yield box
    finally:
        _sinks.reset(token)


def run_in_context(fn, *args, **kwargs):
    """A callable for a thread pool that keeps this context (purpose, deadline, sink)."""
    ctx = contextvars.copy_context()
    return lambda: ctx.run(fn, *args, **kwargs)


def summarize(events: list[UsageEvent]) -> dict:
    llm = [e for e in events if e.kind == "llm"]
    return {
        "llm_calls": len(llm),
        "input_tokens": sum(e.input_tokens for e in llm),
        "output_tokens": sum(e.output_tokens for e in llm),
        "cost_usd": round(sum(e.cost_usd for e in events), 6),
        "embed_calls": sum(1 for e in events if e.kind == "embed"),
        "models": sorted({f"{e.provider}/{e.model}" for e in llm}),
        "cost_by_purpose": _by_purpose(events),
    }


def _by_purpose(events: list[UsageEvent]) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in events:
        key = getattr(e, "purpose", "") or "other"
        out[key] = out.get(key, 0.0) + e.cost_usd
    return {k: round(v, 6) for k, v in out.items()}
