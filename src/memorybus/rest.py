"""REST entry point (Muse skill and other simple clients), protected by a Bearer token."""

from __future__ import annotations

import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .config import Settings
from .service import MemoryBusError, MemoryService, NotFound, SecretRejected

Namespace = Literal[
    "profile",
    "preferences",
    "projects",
    "decisions",
    "environment",
    "goals",
    "current_state",
    "open_loops",
]


class UpsertBody(BaseModel):
    namespace: Namespace
    content: str = Field(min_length=1, max_length=4000)
    subject: str = Field(default="", max_length=200)
    supersedes: str | None = None
    mode: Literal["auto", "new"] = "auto"
    importance: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=0.8, ge=0, le=1)
    expires_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None


def build_router(settings: Settings, service: MemoryService) -> APIRouter:
    bearer = HTTPBearer(auto_error=False)

    def authorize(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        x_memorybus_client: str | None = Header(default=None),
    ) -> str:
        """Check the Bearer token; return the client name used in the event log."""
        expected = settings.api_token
        if not expected:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "MEMORYBUS_API_TOKEN not set")
        if credentials is None or not hmac.compare_digest(
            credentials.credentials.encode(), expected.encode()
        ):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid token", {"WWW-Authenticate": "Bearer"}
            )
        return f"rest:{(x_memorybus_client or 'unknown').strip()[:40]}"

    router = APIRouter(prefix="/v1/memory", tags=["memory"])

    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except SecretRejected as exc:
            raise HTTPException(
                422,
                {"error": "secret_detected", "kinds": exc.kinds, "message": str(exc)},
            ) from exc
        except MemoryBusError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    @router.get("/bootstrap")
    def bootstrap(max_tokens: int = Query(2000, ge=200, le=4000), client=Depends(authorize)):
        return call(service.bootstrap, max_tokens=max_tokens, provider=client)

    @router.get("/search")
    def search(
        q: str = Query(min_length=1, max_length=500),
        limit: int = Query(10, ge=1, le=50),
        namespace: Namespace | None = None,
        include_inactive: bool = False,
        client=Depends(authorize),
    ):
        return call(
            service.search,
            q,
            limit=limit,
            namespace=namespace,
            include_inactive=include_inactive,
            provider=client,
        )

    @router.get("/recent")
    def recent(limit: int = Query(20, ge=1, le=100), client=Depends(authorize)):
        return call(service.recent, limit=limit, provider=client)

    @router.get("/events")
    def events(limit: int = Query(50, ge=1, le=500), _client=Depends(authorize)):
        return call(service.events, limit=limit)

    @router.get("/export", response_model=None)
    def export(format: Literal["json", "md"] = "json", _client=Depends(authorize)):
        if format == "md":
            return PlainTextResponse(call(service.export_markdown), media_type="text/markdown")
        return call(service.export_json)

    @router.get("")
    def list_memories(
        namespace: Namespace | None = None,
        include_inactive: bool = False,
        limit: int = Query(100, ge=1, le=500),
        client=Depends(authorize),
    ):
        return call(
            service.list,
            namespace,
            include_inactive=include_inactive,
            limit=limit,
            provider=client,
        )

    @router.post("", status_code=status.HTTP_200_OK)
    def upsert(body: UpsertBody, client=Depends(authorize)):
        result = call(
            service.upsert,
            body.namespace,
            body.content,
            subject=body.subject,
            supersedes=body.supersedes,
            mode=body.mode,
            importance=body.importance,
            confidence=body.confidence,
            expires_at=body.expires_at,
            metadata=body.metadata,
            conversation_id=body.conversation_id,
            provider=client,
        )
        return result.to_dict()

    @router.get("/{memory_id}")
    def get(memory_id: str, client=Depends(authorize)):
        return call(service.get, memory_id, provider=client)

    @router.put("/{memory_id}")
    def update(memory_id: str, body: UpsertBody, client=Depends(authorize)):
        result = call(
            service.upsert,
            body.namespace,
            body.content,
            subject=body.subject,
            memory_id=memory_id,
            importance=body.importance,
            confidence=body.confidence,
            expires_at=body.expires_at,
            metadata=body.metadata,
            provider=client,
        )
        return result.to_dict()

    @router.delete("/{memory_id}")
    def delete(memory_id: str, client=Depends(authorize)):
        return call(service.delete, memory_id, provider=client)

    return router
