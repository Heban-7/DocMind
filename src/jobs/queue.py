"""A small job queue in Postgres (no extra service to run or pay for).

Workers claim with ``FOR UPDATE SKIP LOCKED``, hold a lease they renew
while working, and a job whose lease ran out (its worker died) is claimed
again. Failed attempts are retried with a growing delay up to
``max_attempts``; after that the job and its document are marked failed.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from uuid import uuid4

from src.db.pool import app_tx, tenant_tx

LEASE_SECONDS = int(os.getenv("DOCMIND_JOB_LEASE_SECONDS", "300"))
RETRY_DELAY_SECONDS = int(os.getenv("DOCMIND_JOB_RETRY_SECONDS", "30"))


def worker_name() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:6]}"


@dataclass(frozen=True)
class Job:
    id: str
    tenant_id: str
    document_id: str
    kind: str
    attempts: int
    max_attempts: int


def enqueue(tenant_id: str, document_id: str, *, conn=None, max_attempts: int = 3) -> str:
    """Add an ingest job for a document (inside the caller's transaction if given)."""
    sql = "INSERT INTO jobs (document_id, max_attempts) VALUES (%s, %s) RETURNING id"
    if conn is not None:
        return str(conn.execute(sql, (document_id, max_attempts)).fetchone()["id"])
    with tenant_tx(tenant_id) as c:
        return str(c.execute(sql, (document_id, max_attempts)).fetchone()["id"])


def claim(worker: str, *, lease_seconds: int = LEASE_SECONDS) -> Job | None:
    """Take the oldest runnable job, or one whose worker stopped renewing it."""
    with app_tx() as conn:
        conn.execute("SELECT set_config('app.worker', 'on', true)")
        row = conn.execute(
            """
            UPDATE jobs SET status = 'running', attempts = attempts + 1, locked_by = %s,
                   locked_until = now() + make_interval(secs => %s), started_at = coalesce(started_at, now()),
                   error = NULL
             WHERE id = (
                   SELECT id FROM jobs
                    WHERE (status = 'queued' AND run_after <= now())
                       OR (status = 'running' AND locked_until < now())
                    ORDER BY run_after, created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1)
            RETURNING id, tenant_id, document_id, kind, attempts, max_attempts
            """,
            (worker, lease_seconds),
        ).fetchone()
    if row is None:
        return None
    return Job(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        document_id=str(row["document_id"]),
        kind=row["kind"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
    )


def renew(job: Job, worker: str, *, lease_seconds: int = LEASE_SECONDS) -> bool:
    """Extend the lease; False if another worker has taken the job over."""
    with app_tx() as conn:
        conn.execute("SELECT set_config('app.worker', 'on', true)")
        row = conn.execute(
            "UPDATE jobs SET locked_until = now() + make_interval(secs => %s)"
            " WHERE id = %s AND locked_by = %s AND status = 'running' RETURNING id",
            (lease_seconds, job.id, worker),
        ).fetchone()
    return row is not None


def complete(job: Job, worker: str) -> None:
    with app_tx() as conn:
        conn.execute("SELECT set_config('app.worker', 'on', true)")
        conn.execute(
            "UPDATE jobs SET status = 'done', finished_at = now(), locked_until = NULL"
            " WHERE id = %s AND locked_by = %s",
            (job.id, worker),
        )


def fail(job: Job, worker: str, error: str) -> bool:
    """Record a failed attempt. Returns True if the job will be retried."""
    retry = job.attempts < job.max_attempts
    with app_tx() as conn:
        conn.execute("SELECT set_config('app.worker', 'on', true)")
        if retry:
            conn.execute(
                "UPDATE jobs SET status = 'queued', error = %s, locked_by = NULL, locked_until = NULL,"
                " run_after = now() + make_interval(secs => %s) WHERE id = %s AND locked_by = %s",
                (error[:2000], RETRY_DELAY_SECONDS * job.attempts, job.id, worker),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status = 'failed', error = %s, finished_at = now(), locked_until = NULL"
                " WHERE id = %s AND locked_by = %s",
                (error[:2000], job.id, worker),
            )
    return retry


def queue_depth() -> dict[str, int]:
    """Jobs per status across all tenants (for the worker's log and health)."""
    with app_tx() as conn:
        conn.execute("SELECT set_config('app.worker', 'on', true)")
        rows = conn.execute("SELECT status, count(*) AS n FROM jobs GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}
