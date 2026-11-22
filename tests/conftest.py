"""Test isolation: runs before any ``src`` module is imported.

* Never load the developer's ``.env`` (no real API keys, no paid calls).
* Point every generated store (profiles, chunks, Chroma, facts, users,
  checkpoints) at a throwaway folder, so tests never write into ``.refinery/``.
* Use a test-only JWT secret.
"""

from __future__ import annotations

import os
import shutil
import tempfile

_TEST_ROOT = tempfile.mkdtemp(prefix="docmind-tests-")

os.environ["DOCMIND_SKIP_DOTENV"] = "1"
os.environ["DOCMIND_REFINERY_DIR"] = os.path.join(_TEST_ROOT, "refinery")
os.environ["DOCMIND_RAW_DIR"] = os.path.join(_TEST_ROOT, "raw")
os.environ["JWT_SECRET_KEY"] = "test-only-secret-not-for-production-" + "x" * 32
os.environ["LANGSMITH_TRACING"] = "false"

# Anything that could route a test to a real provider or a real store.
for _name in (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "LANGSMITH_API_KEY",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_TEXT_MODEL",
    "DOCMIND_CHROMA_DIR",
    "DOCMIND_FACTS_DB",
    "DOCMIND_CHECKPOINTS_DB",
    "DOCMIND_LEGACY_SHARED_DOCS",
):
    os.environ.pop(_name, None)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)
