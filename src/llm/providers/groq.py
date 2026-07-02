"""Groq vision/text client (OpenAI-compatible schema, very fast inference)."""

from __future__ import annotations

from src.llm.providers._openai_compatible import OpenAICompatibleClient


class GroqVisionClient(OpenAICompatibleClient):
    provider = "groq"

    def __init__(self, model: str, api_key: str):
        super().__init__(
            model=model,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
