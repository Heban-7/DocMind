"""Shared HTTP for every provider: one pooled client, timeouts, retries, a deadline.

V1 opened a new connection (and a new TLS handshake) for every call, with a
180 s timeout and no limit on the whole answer: on a slow link one question
could hang for minutes, and each call paid the handshake again (audit P1-6).
Now:

- one ``httpx.Client`` keeps connections alive between calls (and threads);
- connect and read timeouts are separate and short enough to fail fast;
- retries back off on 429 / 5xx / network errors, but never past the
  deadline of the work the call belongs to (``usage.deadline``);
- failures raise ``LLMError`` with a kind, never an empty answer.
"""

from __future__ import annotations

import json as _json
import logging
import os
import threading
import time
from collections.abc import Iterator

import httpx

from src.llm import usage
from src.llm.errors import LLMError

logger = logging.getLogger("docmind.llm")

_RETRY_STATUS = {429, 500, 502, 503, 504}
_BACKOFF_BASE = 0.5  # seconds: 0.5, 1.0, 2.0, ...


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def connect_timeout() -> float:
    return _env_float("DOCMIND_LLM_CONNECT_TIMEOUT_S", 10.0)


def read_timeout() -> float:
    return _env_float("DOCMIND_LLM_READ_TIMEOUT_S", 90.0)


def stream_read_timeout() -> float:
    """Longest wait for the next piece of a stream (the first one included).

    Shorter than ``read_timeout``: a stream that stops mid-answer is better
    given up after this long, leaving time to ask again without streaming.
    """
    return _env_float("DOCMIND_LLM_STREAM_READ_TIMEOUT_S", 25.0)


def max_attempts(kind: str = "") -> int:
    # a dropped connection is usually back within seconds: try longer than for a 5xx
    default = 5 if kind == "network" else 3
    return max(1, int(_env_float("DOCMIND_LLM_MAX_ATTEMPTS", default)))


_client: httpx.Client | None = None
_client_lock = threading.Lock()


def client() -> httpx.Client:
    """The process-wide pooled client (thread-safe; created on first use)."""
    global _client
    with _client_lock:
        if _client is None or _client.is_closed:
            _client = httpx.Client(
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16, keepalive_expiry=90),
                follow_redirects=False,
            )
        return _client


def _timeout(remaining: float | None, read: float | None) -> httpx.Timeout:
    r = read if read is not None else read_timeout()
    c = connect_timeout()
    if remaining is not None:
        r = max(0.5, min(r, remaining))
        c = max(0.5, min(c, remaining))
    return httpx.Timeout(r, connect=c)


def _kind_for_status(code: int) -> str:
    if code == 429:
        return "rate_limit"
    if code in (401, 403):
        return "auth"
    if 400 <= code < 500:
        return "bad_request"
    return "provider"


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        if isinstance(body, list) and body and isinstance(body[0], dict):  # Gemini wraps errors in a list
            return str(body[0].get("error", {}).get("message") or body[0])[:300]
        return str(body)[:300]
    except Exception:
        return response.text[:300]


def _redact(url: str) -> str:
    return url.split("?", 1)[0]


def _check_deadline(provider: str) -> float | None:
    remaining = usage.remaining_seconds()
    if remaining is not None and remaining <= 0.2:
        raise LLMError("the answer ran out of time before this call", kind="deadline", provider=provider)
    return remaining


def _wait_or_give_up(attempt: int, provider: str, kind: str = "") -> bool:
    """Sleep before the next attempt; False when there is no time or no attempt left."""
    if attempt >= max_attempts(kind):
        return False
    wait = _BACKOFF_BASE * (2 ** (attempt - 1))
    remaining = usage.remaining_seconds()
    if remaining is not None and remaining < wait + 1.0:
        return False
    time.sleep(wait)
    return True


def post_json(
    url: str,
    *,
    json: dict,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    provider: str = "",
) -> dict:
    """POST a JSON body and return the parsed JSON, retrying transient failures."""
    attempt = 0
    while True:
        attempt += 1
        remaining = _check_deadline(provider)
        try:
            response = client().post(url, json=json, headers=headers, timeout=_timeout(remaining, timeout))
        except httpx.TimeoutException as exc:
            kind, last = "timeout", exc
        except httpx.TransportError as exc:
            kind, last = "network", exc
        else:
            if response.status_code < 400:
                return response.json()
            message = _error_text(response)
            if response.status_code in _RETRY_STATUS and _wait_or_give_up(attempt, provider):
                logger.warning("LLM HTTP %s from %s (attempt %d); retrying", response.status_code, _redact(url), attempt)
                continue
            raise LLMError(message, kind=_kind_for_status(response.status_code), provider=provider, status=response.status_code)
        logger.warning("LLM %s error calling %s (attempt %d): %s", kind, _redact(url), attempt, type(last).__name__)
        if not _wait_or_give_up(attempt, provider, kind):
            raise LLMError(f"{type(last).__name__} after {attempt} attempt(s)", kind=kind, provider=provider) from last


def stream_sse(
    url: str,
    *,
    json: dict,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    provider: str = "",
) -> Iterator[dict]:
    """POST and yield each server-sent ``data:`` event as parsed JSON.

    Retries happen only before the first event arrives: once text has reached
    the user, a retry would repeat it.
    """
    attempt = 0
    while True:
        attempt += 1
        remaining = _check_deadline(provider)
        started = False
        try:
            wait = timeout if timeout is not None else stream_read_timeout()
            with client().stream("POST", url, json=json, headers=headers, timeout=_timeout(remaining, wait)) as response:
                if response.status_code >= 400:
                    response.read()
                    message = _error_text(response)
                    if response.status_code in _RETRY_STATUS and _wait_or_give_up(attempt, provider):
                        continue
                    raise LLMError(message, kind=_kind_for_status(response.status_code), provider=provider, status=response.status_code)
                for line in response.iter_lines():
                    if usage.remaining_seconds() is not None and usage.remaining_seconds() <= 0:
                        raise LLMError("the answer ran out of time while streaming", kind="deadline", provider=provider)
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        event = _json.loads(data)
                    except ValueError:
                        continue
                    started = True
                    yield event
                return
        except httpx.TimeoutException as exc:
            kind, last = "timeout", exc
        except httpx.TransportError as exc:
            kind, last = "network", exc
        if started or not _wait_or_give_up(attempt, provider, kind):
            raise LLMError(f"{type(last).__name__} while streaming", kind=kind, provider=provider) from last
