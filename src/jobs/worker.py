"""The ingest worker: claims jobs from Postgres and processes documents.

    uv run python -m src.jobs.worker            # run until stopped
    uv run python -m src.jobs.worker --once     # process what is queued, then exit

Run it as its own process next to the API (the API can also start one for
local development, see DOCMIND_EMBEDDED_WORKER). It lowers its own CPU
priority so the API stays responsive while documents are read, keeps its
models loaded between documents, and renews its job lease while it works.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading

from src.jobs import queue

logger = logging.getLogger("docmind.worker")

_stop = threading.Event()


def lower_priority() -> None:
    """Let the API win the CPU when both want it (Linux ``nice 10``).

    Not on Windows: there a below-normal priority class also makes the OS
    throttle the process (power throttling), which measured almost 3x slower
    in M4 (a 12-page report: 54.7 s instead of 19.0 s) for no gain in API
    latency.
    """
    default = "0" if os.name == "nt" else "1"
    if os.getenv("DOCMIND_WORKER_LOW_PRIORITY", default).lower() not in {"1", "true", "yes"}:
        return
    try:
        os.nice(10)
    except Exception as exc:  # not fatal: only scheduling preference
        logger.info("could not lower worker priority: %s", exc)


class _Lease(threading.Thread):
    """Renews the job's lease until stopped; flags the job lost if renewal fails."""

    def __init__(self, job: queue.Job, worker: str, every: float):
        super().__init__(daemon=True)
        self.job, self.worker, self.every = job, worker, every
        self.done = threading.Event()
        self.lost = False

    def run(self) -> None:
        while not self.done.wait(self.every):
            try:
                if not queue.renew(self.job, self.worker):
                    self.lost = True
                    logger.warning("lost the lease on job %s", self.job.id)
                    return
            except Exception as exc:
                logger.warning("lease renewal failed for job %s: %s", self.job.id, exc)


def run_job(job: queue.Job, worker: str, **process_kwargs) -> bool:
    """Process one claimed job. Returns True when the document is ready."""
    from src.db import repos
    from src.pipeline.ingest import process_document

    lease = _Lease(job, worker, every=max(5.0, queue.LEASE_SECONDS / 3))
    lease.start()
    try:
        process_document(job.tenant_id, job.document_id, **process_kwargs)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("job %s failed (attempt %d of %d)", job.id, job.attempts, job.max_attempts)
        retry = queue.fail(job, worker, error)
        try:
            repos.mark_document_failed(job.tenant_id, job.document_id, error, final=not retry)
        except Exception:
            logger.exception("could not record the failure of document %s", job.document_id)
        return False
    finally:
        lease.done.set()
    queue.complete(job, worker)
    return True


def run_once(worker: str | None = None, **process_kwargs) -> int:
    """Process every job that is runnable now; returns how many were run."""
    worker = worker or queue.worker_name()
    n = 0
    while not _stop.is_set():
        job = queue.claim(worker)
        if job is None:
            return n
        run_job(job, worker, **process_kwargs)
        n += 1
    return n


def run_forever(poll_seconds: float = 1.0) -> None:
    from src.db.migrate import migrate

    lower_priority()
    migrate()
    worker = queue.worker_name()
    if os.getenv("DOCMIND_WORKER_WARMUP", "1").lower() in {"1", "true", "yes"}:
        from src.document.docling_engine import warm_up

        logger.info("loading extraction models")
        logger.info("models loaded in %.1fs", warm_up())
    logger.info("worker %s started", worker)
    while not _stop.is_set():
        try:
            if run_once(worker) == 0:
                _stop.wait(poll_seconds)
        except Exception:  # database restart and the like: wait and carry on
            logger.exception("worker loop error")
            _stop.wait(5.0)
    logger.info("worker %s stopped", worker)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m src.jobs.worker")
    ap.add_argument("--once", action="store_true", help="process queued jobs, then exit")
    ap.add_argument("--poll", type=float, default=float(os.getenv("DOCMIND_WORKER_POLL_SECONDS", "1.0")))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: _stop.set())
        except (ValueError, OSError):
            pass
    if args.once:
        lower_priority()
        print(f"processed {run_once()} job(s)")
        return
    run_forever(args.poll)


if __name__ == "__main__":
    main()
