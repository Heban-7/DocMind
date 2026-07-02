"""OpenRouter vision client (OpenAI-compatible, any model slug)."""

from __future__ import annotations

from src.llm.providers._openai_compatible import OpenAICompatibleClient


class OpenRouterVisionClient(OpenAICompatibleClient):
    provider = "openrouter"

    def __init__(self, model: str, api_key: str):
        super().__init__(
            model=model,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            # Optional attribution headers OpenRouter recommends.
            extra_headers={
                "HTTP-Referer": "https://github.com/docmind",
                "X-Title": "DocMind Refinery",
            },
        )
