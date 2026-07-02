"""
The provider-agnostic vision-LLM contract.

Every provider (OpenRouter, OpenAI, Gemini, ...) implements the SAME tiny
interface: take one page image + a prompt, return text plus token usage. The
rest of the system never cares which provider is plugged in -- that's what makes
the credentials interchangeable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VisionResult:
    """One model response, with enough metadata to track spend."""

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class VisionLLMClient(ABC):
    """Abstract vision client: image in, markdown + usage out."""

    #: Provider key, e.g. "openrouter" / "openai" / "gemini".
    provider: str = "base"

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def analyze_image(self, image_png: bytes, prompt: str) -> VisionResult:
        """Send one PNG page image + prompt to the model and return the result."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__} provider='{self.provider}' model='{self.model}'>"
