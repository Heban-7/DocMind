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

from src.llm._http import post_json, stream_sse
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

    def __init__(self, model: str, api_key: str, **_unused):
        super().__init__(model)
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        # The key goes in a header, never in the URL: URLs end up in logs,
        # proxies and error messages (audit P2-12).
        return {"x-goog-api-key": self._api_key}

    def _payload(self, messages, *, response_format=None, temperature=None, max_tokens=None) -> dict:
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
        return payload

    def _result(self, text: str, usage_meta: dict | None, started: float) -> LLMResult:
        usage_meta = usage_meta or {}
        in_tok = int(usage_meta.get("promptTokenCount") or 0)
        # thinking models bill their thoughts as output
        out_tok = int(usage_meta.get("candidatesTokenCount") or 0) + int(usage_meta.get("thoughtsTokenCount") or 0)
        cost = estimate_cost(self.model, in_tok, out_tok)
        latency_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "llm.chat provider=%s model=%s in=%d out=%d cost=$%.5f %.0fms",
            self.provider, self.model, in_tok, out_tok, cost, latency_ms,
        )
        return LLMResult(
            text=text, model=self.model, provider=self.provider,
            input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost, latency_ms=latency_ms,
        )

    @staticmethod
    def _text_of(data: dict) -> str:
        candidates = data.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        return "".join(part.get("text", "") for part in parts if not part.get("thought"))

    def _chat(self, messages: list[Message], **params) -> LLMResult:
        started = time.perf_counter()
        data = post_json(
            f"{_BASE_URL}/{self.model}:generateContent",
            json=self._payload(messages, **params),
            headers=self._headers(),
            provider=self.provider,
        )
        return self._result(self._text_of(data), data.get("usageMetadata"), started)

    def _stream(self, messages: list[Message], **params):
        started = time.perf_counter()
        parts: list[str] = []
        usage_meta: dict | None = None
        for event in stream_sse(
            f"{_BASE_URL}/{self.model}:streamGenerateContent?alt=sse",
            json=self._payload(messages, **params),
            headers=self._headers(),
            provider=self.provider,
        ):
            usage_meta = event.get("usageMetadata") or usage_meta
            piece = self._text_of(event)
            if piece:
                parts.append(piece)
                yield piece
        return self._result("".join(parts), usage_meta, started)
