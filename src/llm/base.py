"""
The provider-agnostic LLM contract.

Every provider (OpenRouter, OpenAI, Gemini, Groq, ...) implements the same
small interface: ``_chat()`` (one request, one reply) and, where the provider
can, ``_stream()`` (the reply as it is written). ``chat()`` and ``stream()``
wrap them with timing and report each call's tokens and cost to the usage
listeners (cost ledger, evaluation meter). Vision is "a message that contains
an image", so ``analyze_image()`` is a thin helper on top of ``chat()``.

Normalized message format (vendor-neutral):
    {"role": "system" | "user" | "assistant", "content": str | list[Part]}
where each Part is one of:
    {"type": "text",  "text": "..."}
    {"type": "image", "image": <png bytes>, "mime": "image/png"}
"""

from __future__ import annotations

import time
from abc import ABC
from collections.abc import Generator, Iterator
from dataclasses import dataclass, field
from typing import Any

from src.llm import usage
from src.llm.errors import LLMError

Message = dict[str, Any]
Part = dict[str, Any]


@dataclass
class LLMResult:
    """One model response, with enough metadata to track spend and latency."""

    text: str
    model: str
    provider: str = "base"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    first_token_ms: float | None = None
    purpose: str = ""


# Backwards-compatible alias: the vision tier historically imported VisionResult.
VisionResult = LLMResult


@dataclass
class ChatStream:
    """Iterate to get the reply's text as it arrives; ``result`` is set at the end."""

    _gen: Generator[str, None, LLMResult]
    result: LLMResult | None = field(default=None, init=False)

    def __iter__(self) -> Iterator[str]:
        self.result = yield from self._gen

    def text(self) -> str:
        """Drain the stream and return the whole reply."""
        return "".join(self)


class LLMClient(ABC):
    """Abstract LLM client: normalized messages in, text + usage out."""

    #: Provider key, e.g. "openrouter" / "openai" / "gemini" / "groq".
    provider: str = "base"

    def __init__(self, model: str):
        self.model = model

    # --- what a provider implements --------------------------------------
    def _chat(self, messages: list[Message], **params) -> LLMResult:
        raise NotImplementedError

    def _stream(self, messages: list[Message], **params) -> Generator[str, None, LLMResult]:
        """Default: no streaming API, so the whole reply arrives as one piece."""
        result = self._chat(messages, **params)
        if result.text:
            yield result.text
        return result

    # --- what callers use -------------------------------------------------
    def chat(
        self,
        messages: list[Message],
        *,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """Send normalized messages to the model and return the result.

        Args:
            messages: normalized messages (see module docstring).
            response_format: pass "json" to request strict JSON output.
            temperature: sampling temperature (None = provider default).
            max_tokens: cap on output tokens (None = provider default).

        Raises:
            LLMError: the call failed after its retries or ran out of time.
        """
        purpose = usage.current_purpose()
        started = time.perf_counter()
        try:
            result = self._chat(messages, response_format=response_format, temperature=temperature, max_tokens=max_tokens)
        except LLMError as exc:
            self._report_failure(exc, started, purpose, streamed=False)
            raise
        result.latency_ms = result.latency_ms or (time.perf_counter() - started) * 1000
        result.purpose = purpose
        self._report(result, streamed=False)
        return result

    def stream(
        self,
        messages: list[Message],
        *,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatStream:
        """Like ``chat()``, but the reply's text arrives piece by piece."""
        return ChatStream(self._streamed(messages, response_format=response_format, temperature=temperature, max_tokens=max_tokens))

    def _streamed(self, messages: list[Message], **params) -> Generator[str, None, LLMResult]:
        if type(self)._chat is LLMClient._chat and type(self)._stream is LLMClient._stream:
            # A client that only overrides chat() (test fakes, old adapters):
            # chat() reports its own usage, so it is not reported twice here.
            started = time.perf_counter()
            result = self.chat(messages, **params)
            if result.text:
                result.first_token_ms = result.first_token_ms or (time.perf_counter() - started) * 1000
                yield result.text
            return result
        purpose = usage.current_purpose()
        started = time.perf_counter()
        try:
            result = yield from _timed(self._stream(messages, **params), started)
        except LLMError as exc:
            self._report_failure(exc, started, purpose, streamed=True)
            raise
        result.latency_ms = (time.perf_counter() - started) * 1000
        result.purpose = purpose
        self._report(result, streamed=True)
        return result

    # --- convenience helpers ---------------------------------------------
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """One-shot text prompt helper."""
        messages: list[Message] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, response_format=response_format, temperature=temperature, max_tokens=max_tokens)

    def analyze_image(self, image_png: bytes, prompt: str) -> LLMResult:
        """Vision helper: send one PNG page image + prompt to the model."""
        messages: list[Message] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "image": image_png, "mime": "image/png"},
                ],
            }
        ]
        return self.chat(messages)

    # --- usage reporting --------------------------------------------------
    def _report(self, result: LLMResult, *, streamed: bool) -> None:
        usage.emit(
            usage.UsageEvent(
                kind="llm",
                provider=result.provider or self.provider,
                model=result.model or self.model,
                purpose=result.purpose,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                first_token_ms=result.first_token_ms,
                streamed=streamed,
            )
        )

    def _report_failure(self, exc: LLMError, started: float, purpose: str, *, streamed: bool) -> None:
        usage.emit(
            usage.UsageEvent(
                kind="llm",
                provider=self.provider,
                model=self.model,
                purpose=purpose,
                latency_ms=(time.perf_counter() - started) * 1000,
                ok=False,
                error_kind=exc.kind,
                streamed=streamed,
            )
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} provider='{self.provider}' model='{self.model}'>"


def _timed(gen: Generator[str, None, LLMResult], started: float) -> Generator[str, None, LLMResult]:
    """Pass the pieces through and stamp the time of the first one on the result."""
    first_ms: float | None = None
    while True:
        try:
            piece = next(gen)
        except StopIteration as stop:
            result: LLMResult = stop.value
            if result.first_token_ms is None:
                result.first_token_ms = first_ms
            return result
        if first_ms is None and piece:
            first_ms = (time.perf_counter() - started) * 1000
        yield piece


# Backwards-compatible alias: earlier code referenced VisionLLMClient.
VisionLLMClient = LLMClient
