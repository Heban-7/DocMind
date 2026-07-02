"""
Shared client for OpenAI-compatible chat APIs (OpenAI itself and OpenRouter).

Both speak the identical `/chat/completions` schema with `image_url` content,
so the only differences are the base URL, auth header, and any extra headers.
"""

from __future__ import annotations

import base64

import httpx

from src.llm.base import VisionLLMClient, VisionResult
from src.llm.pricing import estimate_cost

_TIMEOUT_SECONDS = 180.0


class OpenAICompatibleClient(VisionLLMClient):
    """Vision client for any OpenAI-style `/chat/completions` endpoint."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        extra_headers: dict[str, str] | None = None,
    ):
        super().__init__(model)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._extra_headers = extra_headers or {}

    def analyze_image(self, image_png: bytes, prompt: str) -> VisionResult:
        data_uri = "data:image/png;base64," + base64.b64encode(image_png).decode()

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}", **self._extra_headers}

        response = httpx.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)

        return VisionResult(
            text=text,
            model=self.model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=estimate_cost(self.model, in_tok, out_tok),
        )
