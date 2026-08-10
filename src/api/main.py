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

from src.api.routers import chat_router, health_router, upload_router
from src.api.routes.auth import auth_router, _init_users_table
from src.config import RAW_DIR

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
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    _init_users_table()
    logger.info("DocMind API ready (raw_dir=%s)", RAW_DIR)
    yield


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
