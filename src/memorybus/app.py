"""ASGI app: one Memory Core, two entry points (MCP at /mcp, REST at /v1/memory)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI

from .config import Settings, load_settings
from .db import create_pool, init_schema
from .embeddings import Embedder, build_embedder
from .mcp_server import build_mcp
from .rest import build_router
from .service import MemoryService


def create_app(settings: Settings | None = None, embedder: Embedder | None = None) -> FastAPI:
    settings = settings or load_settings()
    pool = create_pool(settings.database_url)
    init_schema(pool, settings.embedding_dimensions)
    service = MemoryService(pool, embedder or build_embedder(settings))

    mcp = build_mcp(settings, service)
    host = urlparse(settings.public_base_url).hostname
    mcp_app = mcp.http_app(path="/mcp", allowed_hosts=[host] if host else None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp_app.lifespan(app):
            yield
        pool.close()

    app = FastAPI(title="MemoryBus", version="0.1.0", lifespan=lifespan)
    app.state.service = service

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"ok": True, "embeddings": service.embedder is not None}

    app.include_router(build_router(settings, service))
    # Mounted last: serves /mcp plus the OAuth routes (/authorize, /token, /auth/callback,
    # /.well-known/...) that ChatGPT needs at the root of the domain.
    app.mount("/", mcp_app)
    return app
