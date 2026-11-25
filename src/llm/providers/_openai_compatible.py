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

from src.llm._http import post_json, stream_sse
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
                image_url = {"url": f"data:{mime};base64,{b64}"}
                if part.get("detail"):
                    image_url["detail"] = part["detail"]  # "high" to read small print
                parts.append({"type": "image_url", "image_url": image_url})
        out.append({"role": msg["role"], "content": parts})
    return out


class OpenAICompatibleClient(LLMClient):
    """LLM client for any OpenAI-style `/chat/completions` endpoint.

    ``api_style="reasoning"`` is for models that think before they answer
    (OpenAI's gpt-5 family and newer): they take ``max_completion_tokens`` and
    ``reasoning_effort`` and reject ``temperature``.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        extra_headers: dict[str, str] | None = None,
        *,
        api_style: str = "chat",
        reasoning_effort: str | None = None,
    ):
        super().__init__(model)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._extra_headers = extra_headers or {}
        self.api_style = api_style
        self.reasoning_effort = reasoning_effort

    def _payload(self, messages, *, response_format=None, temperature=None, max_tokens=None) -> dict:
        payload: dict = {"model": self.model, "messages": _to_openai_messages(messages)}
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        if self.api_style == "reasoning":
            if max_tokens is not None:
                # thinking tokens count against this cap too
                payload["max_completion_tokens"] = max_tokens + 1024
            if self.reasoning_effort:
                payload["reasoning_effort"] = self.reasoning_effort
        else:
            if temperature is not None:
                payload["temperature"] = temperature
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
        return payload

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", **self._extra_headers}

    def _result(self, text: str, usage_block: dict | None, started: float) -> LLMResult:
        usage_block = usage_block or {}
        in_tok = int(usage_block.get("prompt_tokens") or 0)
        out_tok = int(usage_block.get("completion_tokens") or 0)
        cost = estimate_cost(self.model, in_tok, out_tok)
        latency_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "llm.chat provider=%s model=%s in=%d out=%d cost=$%.5f %.0fms",
            self.provider, self.model, in_tok, out_tok, cost, latency_ms,
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

    def _chat(self, messages: list[Message], **params) -> LLMResult:
        started = time.perf_counter()
        data = post_json(
            f"{self._base_url}/chat/completions",
            json=self._payload(messages, **params),
            headers=self._headers(),
            provider=self.provider,
        )
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return self._result(text, data.get("usage"), started)

    def _stream(self, messages: list[Message], **params):
        started = time.perf_counter()
        payload = self._payload(messages, **params)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        parts: list[str] = []
        usage_block: dict | None = None
        for event in stream_sse(
            f"{self._base_url}/chat/completions", json=payload, headers=self._headers(), provider=self.provider
        ):
            # OpenAI and OpenRouter put usage in the last chunk; Groq under x_groq
            usage_block = event.get("usage") or (event.get("x_groq") or {}).get("usage") or usage_block
            for choice in event.get("choices") or []:
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    parts.append(piece)
                    yield piece
        return self._result("".join(parts), usage_block, started)
