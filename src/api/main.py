"""
DocMind API Gateway (FastAPI).

Exposes the document intelligence pipeline to web frontends:

  GET  /health
  POST /upload
  POST /chat
  GET  /history/{thread_id}

Dev server:

    uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.auth_utils import jwt_secret
from src.api.routers import chat_router, health_router, upload_router
from src.api.routes.auth import auth_router

logger = logging.getLogger("docmind.api")

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _cors_origins() -> list[str]:
    raw = os.getenv("DOCMIND_CORS_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Refuse to start with a missing or publicly known signing secret.
    jwt_secret()
    if os.getenv("DOCMIND_AUTO_MIGRATE", "1").lower() in {"1", "true", "yes"}:
        from src.db.migrate import migrate

        applied = migrate()
        if applied:
            logger.info("applied migrations: %s", ", ".join(applied))
    worker = _start_embedded_worker()
    logger.info("DocMind API ready")
    yield
    if worker is not None:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except Exception:
            worker.kill()
    from src.db.pool import close_pool

    close_pool()


def _start_embedded_worker():
    """For local development: run the ingest worker as a child process.

    The worker is a separate process (never a thread of the API), so reading
    a large PDF cannot slow the API down. In production run it on its own
    (``python -m src.jobs.worker``) and set DOCMIND_EMBEDDED_WORKER=0.
    """
    if os.getenv("DOCMIND_EMBEDDED_WORKER", "1").lower() not in {"1", "true", "yes"}:
        return None
    import subprocess
    import sys

    logger.info("starting an embedded ingest worker process")
    return subprocess.Popen([sys.executable, "-m", "src.jobs.worker"])


def create_app() -> FastAPI:
    """Application factory (used by uvicorn and tests)."""
    app = FastAPI(
        title="DocMind API",
        description=(
            "Document Intelligence Refinery gateway: upload PDFs, "
            "query with provenance, and resume chat threads."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(upload_router)
    app.include_router(chat_router)
    return app


app = create_app()
