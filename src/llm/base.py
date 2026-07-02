"""
The provider-agnostic LLM contract.

Every provider (OpenRouter, OpenAI, Gemini, Groq, ...) implements the SAME small
interface. There is exactly ONE primitive to implement -- `chat()` -- which
takes a list of normalized messages (optionally containing images) and returns
text plus token/cost usage. Vision is just "a message that contains an image",
so `analyze_image()` is a thin concrete helper built on top of `chat()`.

This is what makes the credentials and models interchangeable: the rest of the
system depends on this contract, never on a specific vendor's SDK or wire shape.

Normalized message format (vendor-neutral):
    {"role": "system" | "user" | "assistant", "content": str | list[Part]}
where each Part is one of:
    {"type": "text",  "text": "..."}
    {"type": "image", "image": <png bytes>, "mime": "image/png"}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

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


# Backwards-compatible alias: the vision tier historically imported VisionResult.
VisionResult = LLMResult


class LLMClient(ABC):
    """Abstract LLM client: normalized messages in, text + usage out."""

    #: Provider key, e.g. "openrouter" / "openai" / "gemini" / "groq".
    provider: str = "base"

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
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
        """
        raise NotImplementedError

    # --- Convenience helpers (concrete; built on top of chat) ---------------
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
        return self.chat(
            messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

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

    def __repr__(self) -> str:
        return f"<{type(self).__name__} provider='{self.provider}' model='{self.model}'>"


# Backwards-compatible alias: earlier code referenced VisionLLMClient.
VisionLLMClient = LLMClient
