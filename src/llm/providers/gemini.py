"""
Direct Google Gemini vision client.

Gemini uses a different request/response shape from the OpenAI-style APIs, so it
gets its own implementation of the same `analyze_image` contract.
"""

from __future__ import annotations

import base64

import httpx

from src.llm.base import VisionLLMClient, VisionResult
from src.llm.pricing import estimate_cost

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT_SECONDS = 180.0


class GeminiVisionClient(VisionLLMClient):
    provider = "gemini"

    def __init__(self, model: str, api_key: str):
        super().__init__(model)
        self._api_key = api_key

    def analyze_image(self, image_png: bytes, prompt: str) -> VisionResult:
        b64 = base64.b64encode(image_png).decode()
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": b64}},
                    ]
                }
            ]
        }

        url = f"{_BASE_URL}/{self.model}:generateContent?key={self._api_key}"
        response = httpx.post(url, json=payload, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()

        parts = data["candidates"][0]["content"].get("parts", [])
        text = "".join(part.get("text", "") for part in parts)

        usage = data.get("usageMetadata", {})
        in_tok = usage.get("promptTokenCount", 0)
        out_tok = usage.get("candidatesTokenCount", 0)

        return VisionResult(
            text=text,
            model=self.model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=estimate_cost(self.model, in_tok, out_tok),
        )
