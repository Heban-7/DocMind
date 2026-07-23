"""
LangSmith observability for DocMind agents (STEP 3).

Analogy: the control-tower recording of every flight -- each Query Agent run
becomes a trace you can replay in the LangSmith UI (nodes, tools, latency).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("docmind.observability")


@dataclass(frozen=True)
class LangSmithStatus:
    """Snapshot of whether tracing is active for this process."""

    enabled: bool
    project: str
    api_key_present: bool
    reason: str


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_langsmith(
    *,
    enabled: bool | None = None,
    project: str | None = None,
    api_key: str | None = None,
) -> LangSmithStatus:
    """Enable LangSmith / LangChain tracing via environment variables.

    Preferred env vars (set in ``.env``):
      - LANGSMITH_API_KEY   (required to upload traces)
      - LANGSMITH_TRACING=true
      - LANGSMITH_PROJECT=docmind  (optional; default DocMind)

    Also sets the legacy ``LANGCHAIN_TRACING_V2`` / ``LANGCHAIN_API_KEY`` /
    ``LANGCHAIN_PROJECT`` aliases so LangGraph picks up tracing reliably.
    """
    key = (api_key if api_key is not None else os.getenv("LANGSMITH_API_KEY") or "").strip()
    if not key:
        # Accept legacy LangChain-named key.
        key = (os.getenv("LANGCHAIN_API_KEY") or "").strip()

    project_name = (
        project
        or os.getenv("LANGSMITH_PROJECT")
        or os.getenv("LANGCHAIN_PROJECT")
        or "docmind"
    ).strip() or "docmind"

    if enabled is None:
        # Auto-enable when a key is present unless explicitly disabled.
        explicit = os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2")
        if explicit is not None and explicit.strip() != "":
            want = _truthy(explicit)
        else:
            want = bool(key)
    else:
        want = bool(enabled)

    if want and not key:
        # Do not pretend tracing works without credentials.
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        status = LangSmithStatus(
            enabled=False,
            project=project_name,
            api_key_present=False,
            reason="LANGSMITH_API_KEY missing; tracing left off.",
        )
        logger.info("LangSmith: %s", status.reason)
        return status

    if not want:
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        status = LangSmithStatus(
            enabled=False,
            project=project_name,
            api_key_present=bool(key),
            reason="Tracing disabled (LANGSMITH_TRACING=false).",
        )
        logger.info("LangSmith: %s", status.reason)
        return status

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGCHAIN_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = project_name
    os.environ["LANGCHAIN_PROJECT"] = project_name

    status = LangSmithStatus(
        enabled=True,
        project=project_name,
        api_key_present=True,
        reason=f"Tracing on -> project '{project_name}'.",
    )
    logger.info("LangSmith: %s", status.reason)
    return status


def tracing_enabled() -> bool:
    """Return True when LangSmith upload is configured for this process."""
    return _truthy(os.getenv("LANGSMITH_TRACING")) and bool(
        (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY") or "").strip()
    )


def traceable_run(name: str):
    """Decorator factory: no-op when langsmith is unavailable; else ``@traceable``.

    Use on high-level entry points (``ask``, ``audit``, ``route_intent``) so
    custom LLMClient work still appears as nested spans under the LangGraph run.
    """
    try:
        from langsmith import traceable
    except Exception:  # pragma: no cover
        def _identity(fn):
            return fn

        return _identity

    return traceable(name=name, run_type="chain")
