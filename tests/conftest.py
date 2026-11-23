"""Test isolation: runs before any ``src`` module is imported.

* Never load the developer's ``.env`` (no real API keys, no paid calls).
* Point generated files (stored PDFs, document models) at a throwaway folder.
* Use a test-only JWT secret.
* Database tests use their own database (``docmind_test`` on the dev server
  by default, or ``DOCMIND_TEST_DATABASE_URL``), never the dev database. They
  are skipped when no database is reachable, unless ``DOCMIND_REQUIRE_DB=1``
  (CI), where a missing database is a failure.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

_TEST_ROOT = tempfile.mkdtemp(prefix="docmind-tests-")

os.environ["DOCMIND_SKIP_DOTENV"] = "1"
os.environ["DOCMIND_REFINERY_DIR"] = os.path.join(_TEST_ROOT, "refinery")
os.environ["DOCMIND_STORAGE_DIR"] = os.path.join(_TEST_ROOT, "storage")
os.environ["JWT_SECRET_KEY"] = "test-only-secret-not-for-production-" + "x" * 32
os.environ["LANGSMITH_TRACING"] = "false"

_TEST_DB_URL = os.getenv(
    "DOCMIND_TEST_DATABASE_URL",
    "postgresql://docmind:docmind-dev-only@localhost:5433/docmind_test",
)
os.environ["DOCMIND_DATABASE_URL"] = _TEST_DB_URL
os.environ.pop("DOCMIND_DATABASE_ADMIN_URL", None)

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
    "DOCMIND_API_SKIP_EMBED",
):
    os.environ.pop(_name, None)


def _ensure_test_database() -> bool:
    """Create the test database on the server if it is missing."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    try:
        with psycopg.connect(_TEST_DB_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError as exc:
        if "does not exist" not in str(exc):
            return False
    params = conninfo_to_dict(_TEST_DB_URL)
    name = params.get("dbname")
    try:
        with psycopg.connect(make_conninfo(**{**params, "dbname": "postgres"}), autocommit=True, connect_timeout=2) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        return True
    except psycopg.Error:
        return False


@pytest.fixture(scope="session")
def pg():
    """A freshly migrated test database (once per session)."""
    if not _ensure_test_database():
        if os.getenv("DOCMIND_REQUIRE_DB") == "1":
            pytest.fail(f"database required but not reachable: {_TEST_DB_URL}")
        pytest.skip("no Postgres reachable (start it: docker compose -f docker-compose.dev.yml up -d db)")
    from src.db.migrate import reset_for_tests
    from src.db.pool import close_pool

    reset_for_tests()
    yield
    close_pool()


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)
