"""
Direct Google Gemini client.

Gemini uses a different request/response shape from the OpenAI-style APIs, so it
translates the normalized messages into its own `contents` format while
implementing the same `chat()` contract.
"""

from __future__ import annotations

import base64
import logging
import time

from src.llm._http import post_json
from src.llm.base import LLMClient, LLMResult, Message
from src.llm.pricing import estimate_cost

logger = logging.getLogger("docmind.llm")

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _to_gemini(messages: list[Message]) -> tuple[list[dict], str | None]:
    """Return (contents, system_instruction_text) for the Gemini API."""
    contents: list[dict] = []
    system_texts: list[str] = []

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "system":
            if isinstance(content, str):
                system_texts.append(content)
            continue

        parts: list[dict] = []
        if isinstance(content, str):
            parts.append({"text": content})
        else:
            for part in content:
                if part["type"] == "text":
                    parts.append({"text": part["text"]})
                elif part["type"] == "image":
                    parts.append(
                        {
                            "inline_data": {
                                "mime_type": part.get("mime", "image/png"),
                                "data": base64.b64encode(part["image"]).decode(),
                            }
                        }
                    )
        # Gemini uses "model" for assistant turns.
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": parts})

    system = "\n".join(system_texts) if system_texts else None
    return contents, system


class GeminiVisionClient(LLMClient):
    provider = "gemini"

    def __init__(self, model: str, api_key: str):
        super().__init__(model)
        self._api_key = api_key

    def chat(
        self,
        messages: list[Message],
        *,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        contents, system = _to_gemini(messages)
        payload: dict = {"contents": contents}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        gen_cfg: dict = {}
        if response_format == "json":
            gen_cfg["response_mime_type"] = "application/json"
        if temperature is not None:
            gen_cfg["temperature"] = temperature
        if max_tokens is not None:
            gen_cfg["maxOutputTokens"] = max_tokens
        if gen_cfg:
            payload["generationConfig"] = gen_cfg

        url = f"{_BASE_URL}/{self.model}:generateContent?key={self._api_key}"

        started = time.perf_counter()
        data = post_json(url, json=payload)
        latency_ms = (time.perf_counter() - started) * 1000

        candidates = data.get("candidates", [])
        parts = (
            candidates[0].get("content", {}).get("parts", []) if candidates else []
        )
        text = "".join(part.get("text", "") for part in parts)

        usage = data.get("usageMetadata", {})
        in_tok = usage.get("promptTokenCount", 0)
        out_tok = usage.get("candidatesTokenCount", 0)
        cost = estimate_cost(self.model, in_tok, out_tok)

        logger.info(
            "llm.chat provider=%s model=%s in=%d out=%d cost=$%.5f %.0fms",
            self.provider,
            self.model,
            in_tok,
            out_tok,
            cost,
            latency_ms,
        )
        return LLMResult(
            text=text,
            model=self.model,
            provider=self.provider,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
