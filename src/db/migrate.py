"""Apply SQL migrations in order, once each, and set up the chat checkpointer.

    python -m src.db.migrate
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.db.pool import APP_ROLE, admin_connection

logger = logging.getLogger("docmind.db")
MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def migrate() -> list[str]:
    applied: list[str] = []
    with admin_connection() as conn:
        # Two API workers starting at once must not apply the same file twice.
        conn.execute("SELECT pg_advisory_lock(7238410)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
        )
        done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
            logger.info("applied migration %s", path.name)
        _setup_checkpointer(conn)
    return applied


def _setup_checkpointer(conn) -> None:
    """Create LangGraph's checkpoint tables and let the app role use them."""
    from langgraph.checkpoint.postgres import PostgresSaver

    PostgresSaver(conn).setup()
    for row in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'checkpoint%%'"
    ).fetchall():
        conn.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{row["tablename"]}" TO {APP_ROLE}')


def reset_for_tests() -> None:
    """Drop everything and re-apply migrations. Only ever used by tests."""
    with admin_connection() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
    migrate()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(migrate() or "up to date")
