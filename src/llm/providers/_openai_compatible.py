"""
Shared client for OpenAI-compatible chat APIs (OpenAI, OpenRouter, Groq).

They all speak the identical `/chat/completions` schema with `image_url` content
parts, so they share this one implementation. The only differences are the base
URL, auth header, and any extra headers -- set by the thin subclasses.
"""

from __future__ import annotations

import base64
import logging
import time

from src.llm._http import post_json
from src.llm.base import LLMClient, LLMResult, Message
from src.llm.pricing import estimate_cost

logger = logging.getLogger("docmind.llm")


def _to_openai_messages(messages: list[Message]) -> list[dict]:
    """Translate normalized messages into OpenAI `content` parts."""
    out: list[dict] = []
    for msg in messages:
        content = msg["content"]
        if isinstance(content, str):
            out.append({"role": msg["role"], "content": content})
            continue

        parts: list[dict] = []
        for part in content:
            if part["type"] == "text":
                parts.append({"type": "text", "text": part["text"]})
            elif part["type"] == "image":
                mime = part.get("mime", "image/png")
                b64 = base64.b64encode(part["image"]).decode()
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    }
                )
        out.append({"role": msg["role"], "content": parts})
    return out


class OpenAICompatibleClient(LLMClient):
    """LLM client for any OpenAI-style `/chat/completions` endpoint."""

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

    def chat(
        self,
        messages: list[Message],
        *,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        payload: dict = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            **self._extra_headers,
        }

        started = time.perf_counter()
        data = post_json(
            f"{self._base_url}/chat/completions", json=payload, headers=headers
        )
        latency_ms = (time.perf_counter() - started) * 1000

        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
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
