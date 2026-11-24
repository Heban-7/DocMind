"""The shared HTTP layer: pooled client, retries, deadline, errors with a kind; streaming; usage."""

from __future__ import annotations

import json

import httpx
import pytest

from src.llm import _http, usage
from src.llm.errors import LLMError
from src.llm.providers.openai import OpenAIVisionClient


@pytest.fixture()
def transport(monkeypatch):
    """Route the pooled client through a handler the test controls."""
    box = {"handler": None, "calls": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        box["calls"] += 1
        return box["handler"](request)

    monkeypatch.setattr(_http, "_client", httpx.Client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(_http, "_BACKOFF_BASE", 0.01)
    return box


def _ok(text="hi", prompt=10, completion=2):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": prompt, "completion_tokens": completion}})


def test_retries_a_429_then_succeeds(transport):
    seq = [httpx.Response(429, json={"error": {"message": "slow down"}}), _ok()]
    transport["handler"] = lambda r: seq.pop(0)
    out = _http.post_json("https://api.example/v1/chat", json={}, provider="openai")
    assert out["choices"][0]["message"]["content"] == "hi" and transport["calls"] == 2


def test_a_timeout_raises_an_error_with_its_kind(transport):
    def boom(request):
        raise httpx.ReadTimeout("read timed out", request=request)

    transport["handler"] = boom
    with pytest.raises(LLMError) as info:
        _http.post_json("https://api.example/v1/chat", json={}, provider="openai")
    assert info.value.kind == "timeout" and transport["calls"] == _http.max_attempts("timeout")
    assert info.value.http_status == 504


def test_a_bad_key_is_not_retried(transport):
    transport["handler"] = lambda r: httpx.Response(401, json={"error": {"message": "Incorrect API key"}})
    with pytest.raises(LLMError) as info:
        _http.post_json("https://api.example/v1/chat", json={}, provider="openai")
    assert info.value.kind == "auth" and transport["calls"] == 1
    assert "rejected the API key" in info.value.user_message()


def test_no_call_is_made_after_the_deadline(transport):
    transport["handler"] = lambda r: _ok()
    with usage.deadline(0.0):
        with pytest.raises(LLMError) as info:
            _http.post_json("https://api.example/v1/chat", json={}, provider="openai")
    assert info.value.kind == "deadline" and transport["calls"] == 0


def test_streaming_yields_pieces_and_reports_usage_once(transport):
    lines = [
        {"choices": [{"delta": {"content": "Hel"}}]},
        {"choices": [{"delta": {"content": "lo"}}]},
        {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
    ]
    body = "".join(f"data: {json.dumps(x)}\n\n" for x in lines) + "data: [DONE]\n\n"
    transport["handler"] = lambda r: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    client = OpenAIVisionClient("gpt-4o-mini", "sk-test")
    with usage.purpose("answer"), usage.collect() as outer, usage.collect() as inner:
        stream = client.stream([{"role": "user", "content": "hi"}])
        assert list(stream) == ["Hel", "lo"]
    assert stream.result.text == "Hello" and stream.result.input_tokens == 12
    assert stream.result.first_token_ms is not None
    assert len(outer) == len(inner) == 1  # nested collectors both see the one call
    e = inner[0]
    assert (e.purpose, e.streamed, e.output_tokens, e.ok) == ("answer", True, 3, True)
    assert e.cost_usd == pytest.approx((12 * 0.15 + 3 * 0.60) / 1e6)


def test_a_failed_call_is_reported_as_failed(transport):
    transport["handler"] = lambda r: httpx.Response(400, json={"error": {"message": "bad"}})
    with usage.collect() as events, pytest.raises(LLMError):
        OpenAIVisionClient("gpt-4o-mini", "sk-test").chat([{"role": "user", "content": "hi"}])
    assert len(events) == 1 and not events[0].ok and events[0].error_kind == "bad_request"


def test_one_pooled_client_is_reused():
    assert _http.client() is _http.client()
