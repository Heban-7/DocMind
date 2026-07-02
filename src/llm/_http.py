"""
Shared HTTP helper: POST JSON with retries + exponential backoff.

All providers hit flaky networks and transient rate limits (HTTP 429) or server
errors (5xx). Centralizing the retry policy here keeps every provider resilient
without duplicating the logic.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger("docmind.llm")

_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5  # seconds: 0.5, 1.0, 2.0, ...
_TIMEOUT_SECONDS = 180.0


def post_json(
    url: str,
    *,
    json: dict,
    headers: dict[str, str] | None = None,
    timeout: float = _TIMEOUT_SECONDS,
) -> dict:
    """POST a JSON body and return the parsed JSON, retrying transient failures."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = httpx.post(url, json=json, headers=headers, timeout=timeout)
            if response.status_code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "LLM HTTP %s (attempt %d/%d); retrying in %.1fs",
                    response.status_code,
                    attempt,
                    _MAX_ATTEMPTS,
                    wait,
                )
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt >= _MAX_ATTEMPTS:
                break
            wait = _BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(
                "LLM network error (attempt %d/%d): %s; retrying in %.1fs",
                attempt,
                _MAX_ATTEMPTS,
                exc,
                wait,
            )
            time.sleep(wait)

    raise RuntimeError(
        f"LLM request to {url} failed after {_MAX_ATTEMPTS} attempts"
    ) from last_exc
