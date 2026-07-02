"""Direct OpenAI vision client (OpenAI-compatible schema)."""

from __future__ import annotations

from src.llm.providers._openai_compatible import OpenAICompatibleClient


class OpenAIVisionClient(OpenAICompatibleClient):
    provider = "openai"

    def __init__(self, model: str, api_key: str):
        super().__init__(
            model=model,
            api_key=api_key,
            base_url="https://api.openai.com/v1",
        )
