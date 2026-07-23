"""Offline tests for LangSmith configuration (no network upload required)."""

from __future__ import annotations

import os

from src.observability.langsmith import configure_langsmith, tracing_enabled


def test_configure_langsmith_off_without_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)

    status = configure_langsmith(enabled=True, project="docmind-test")
    assert status.enabled is False
    assert status.api_key_present is False
    assert tracing_enabled() is False


def test_configure_langsmith_on_with_key(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)

    status = configure_langsmith(enabled=True, project="docmind-test")
    assert status.enabled is True
    assert status.project == "docmind-test"
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert tracing_enabled() is True

    # Cleanup so later tests stay offline.
    configure_langsmith(enabled=False)


def test_configure_langsmith_explicit_disable(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_fake_key")
    status = configure_langsmith(enabled=False, project="docmind-test")
    assert status.enabled is False
    assert tracing_enabled() is False
