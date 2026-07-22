"""
SQLite-backed FactTable store.

Analogy: a spreadsheet of "metric / value / period" rows, each stamped with
page + content hash so auditors can verify the number against the PDF.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from src.config import FACTS_DB_PATH
from src.facts.models import FactRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    document_name TEXT NOT NULL DEFAULT '',
    metric TEXT NOT NULL,
    value REAL,
    value_text TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    period TEXT NOT NULL DEFAULT '',
    page_number INTEGER NOT NULL DEFAULT 1,
    content_hash TEXT NOT NULL DEFAULT '',
    chunk_id TEXT NOT NULL DEFAULT '',
    source_excerpt TEXT NOT NULL DEFAULT '',
    extractor TEXT NOT NULL DEFAULT 'heuristic',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_doc ON facts(doc_id);
CREATE INDEX IF NOT EXISTS idx_facts_metric ON facts(metric);
CREATE INDEX IF NOT EXISTS idx_facts_period ON facts(period);
"""


class FactStore:
    """Thin SQLite wrapper for FactRecord rows."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path or FACTS_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def delete_doc(self, doc_id: str) -> int:
        cur = self._conn.execute("DELETE FROM facts WHERE doc_id = ?", (doc_id,))
        self._conn.commit()
        return cur.rowcount

    def upsert_many(self, facts: list[FactRecord]) -> int:
        if not facts:
            return 0
        rows = [
            (
                f.id,
                f.doc_id,
                f.document_name,
                f.metric,
                f.value,
                f.value_text,
                f.unit,
                f.period,
                f.page_number,
                f.content_hash,
                f.chunk_id,
                f.source_excerpt,
                f.extractor,
                f.created_at.isoformat(),
            )
            for f in facts
        ]
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO facts (
                id, doc_id, document_name, metric, value, value_text, unit,
                period, page_number, content_hash, chunk_id, source_excerpt,
                extractor, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()
        return len(rows)

    def replace_doc_facts(self, doc_id: str, facts: list[FactRecord]) -> int:
        """Idempotent: wipe prior facts for doc_id, then insert ``facts``."""
        self.delete_doc(doc_id)
        return self.upsert_many(facts)

    def count(self, doc_id: str | None = None) -> int:
        if doc_id:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM facts WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()
        return int(row["n"])

    def search(
        self,
        *,
        doc_id: str | None = None,
        metric_contains: str | None = None,
        period_contains: str | None = None,
        limit: int = 50,
    ) -> list[FactRecord]:
        """Filtered lookup used by structured_query (safe, parameterized)."""
        clauses: list[str] = []
        params: list = []
        if doc_id:
            clauses.append("doc_id = ?")
            params.append(doc_id)
        if metric_contains:
            clauses.append("LOWER(metric) LIKE ?")
            params.append(f"%{metric_contains.lower()}%")
        if period_contains:
            clauses.append("LOWER(period) LIKE ?")
            params.append(f"%{period_contains.lower()}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM facts{where} ORDER BY page_number, metric LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def select(self, sql: str, params: tuple | list | None = None) -> list[dict]:
        """Read-only SQL for power users / structured_query.

        Only SELECT statements are allowed (blocks DROP/UPDATE/... injection).
        """
        cleaned = sql.strip().rstrip(";").strip()
        if not cleaned.lower().startswith("select"):
            raise ValueError("FactStore.select only allows SELECT statements.")
        forbidden = (" insert ", " update ", " delete ", " drop ", " alter ",
                     " attach ", " pragma ", " create ", " replace ")
        padded = f" {cleaned.lower()} "
        if any(tok in padded for tok in forbidden):
            raise ValueError("FactStore.select rejected a non-read-only SQL clause.")
        cur = self._conn.execute(cleaned, params or [])
        return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> FactRecord:
        return FactRecord(
            id=row["id"],
            doc_id=row["doc_id"],
            document_name=row["document_name"],
            metric=row["metric"],
            value=row["value"],
            value_text=row["value_text"],
            unit=row["unit"] or "",
            period=row["period"] or "",
            page_number=row["page_number"],
            content_hash=row["content_hash"] or "",
            chunk_id=row["chunk_id"] or "",
            source_excerpt=row["source_excerpt"] or "",
            extractor=row["extractor"] or "heuristic",
            created_at=datetime.fromisoformat(row["created_at"]),
        )
