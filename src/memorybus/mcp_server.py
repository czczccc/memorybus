"""MCP entry point (ChatGPT and other MCP clients), protected by GitHub OAuth."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import AuthMiddleware
from fastmcp.utilities.authorization import AuthContext
from pydantic import Field

from .config import Settings
from .service import NAMESPACES, MemoryBusError, MemoryService

INSTRUCTIONS = """\
MemoryBus is the user's own long-term memory, shared across all of their AI assistants.
- At the start of every new conversation, call memory_bootstrap and use the packet as
  background about the user.
- When the user refers to past context you don't have, call memory_search.
- When the user states durable information (who they are, preferences, environment,
  projects, decisions, goals, current state, open loops), call memory_upsert. Do not
  save one-off chit-chat, and never save passwords, keys, tokens or codes.
- Write each memory as one self-contained fact in the third person ("User prefers uv
  for Python projects"). `subject` is the key: a new memory with the same namespace and
  subject replaces the old one, so make subjects specific ("JobAgent Studio / database").
"""

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


def _client_name(ctx: Context | None) -> str:
    """Best-effort name of the calling AI client, used in the event log."""
    try:
        params = ctx.session.client_params  # type: ignore[union-attr]
        info = getattr(params, "client_info", None) or getattr(params, "clientInfo", None)
        name = getattr(info, "name", None)
        if name:
            return f"mcp:{name}"[:64]
    except Exception:
        pass
    return "mcp"


def _is_local(url: str) -> bool:
    return urlparse(url).hostname in ("localhost", "127.0.0.1", "::1")


def owner_only(allowed_logins: list[str]):
    """Auth check that admits only the configured GitHub accounts."""

    def check(auth: AuthContext) -> bool:
        if auth.token is None:
            return False
        login = str(auth.token.claims.get("login") or "").lower()
        return login in allowed_logins

    return check


def build_mcp(settings: Settings, service: MemoryService) -> FastMCP:
    auth = None
    middleware = []
    if not settings.oauth_enabled and not _is_local(settings.public_base_url):
        raise RuntimeError(
            "Refusing to serve /mcp publicly without OAuth: set GITHUB_CLIENT_ID and "
            "GITHUB_CLIENT_SECRET, or use a localhost PUBLIC_BASE_URL for development"
        )
    if settings.oauth_enabled:
        from fastmcp.server.auth.providers.github import GitHubProvider

        if not settings.allowed_github_logins:
            raise RuntimeError("Set ALLOWED_GITHUB_LOGINS when GitHub OAuth is enabled")
        auth = GitHubProvider(
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
            base_url=settings.public_base_url,
            jwt_signing_key=settings.jwt_signing_key,
        )
        middleware.append(AuthMiddleware(auth=owner_only(settings.allowed_github_logins)))

    mcp = FastMCP("MemoryBus", instructions=INSTRUCTIONS, auth=auth, middleware=middleware)

    def run(fn, *args, **kwargs) -> Any:
        try:
            return fn(*args, **kwargs)
        except MemoryBusError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations={"readOnlyHint": True})
    def memory_bootstrap(
        ctx: Context,
        max_tokens: Annotated[int, Field(ge=200, le=4000)] = 2000,
    ) -> dict:
        """Get the user's Memory Packet (profile, preferences, environment, active projects,
        current state, recent decisions, goals, open loops). Call once at the start of
        every new conversation."""
        return run(service.bootstrap, max_tokens=max_tokens, provider=_client_name(ctx))

    @mcp.tool(annotations={"readOnlyHint": True})
    def memory_search(
        ctx: Context,
        query: Annotated[str, Field(description="What to look for, in natural language")],
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
        namespace: Namespace | None = None,
        include_inactive: Annotated[
            bool, Field(description="Also return superseded memories (history)")
        ] = False,
    ) -> list[dict]:
        """Search the user's long-term memories relevant to the current question."""
        return run(
            service.search,
            query,
            limit=limit,
            namespace=namespace,
            include_inactive=include_inactive,
            provider=_client_name(ctx),
        )

    @mcp.tool(annotations={"readOnlyHint": True})
    def memory_get(ctx: Context, id: str) -> dict:
        """Get one memory by id."""
        return run(service.get, id, provider=_client_name(ctx))

    @mcp.tool(annotations={"readOnlyHint": True})
    def memory_list(
        ctx: Context,
        namespace: Namespace | None = None,
        include_inactive: bool = False,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> list[dict]:
        """List memories, optionally for one namespace."""
        return run(
            service.list,
            namespace,
            include_inactive=include_inactive,
            limit=limit,
            provider=_client_name(ctx),
        )

    @mcp.tool(annotations={"readOnlyHint": True})
    def memory_recent(ctx: Context, limit: Annotated[int, Field(ge=1, le=100)] = 20) -> list[dict]:
        """Memories that changed most recently."""
        return run(service.recent, limit=limit, provider=_client_name(ctx))

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False})
    def memory_upsert(
        ctx: Context,
        namespace: Namespace,
        content: Annotated[str, Field(description="One self-contained durable fact")],
        subject: Annotated[
            str, Field(description="Specific key; same namespace+subject replaces the old memory")
        ] = "",
        id: Annotated[str | None, Field(description="Update this memory in place")] = None,
        supersedes: Annotated[
            str | None, Field(description="Id of a memory this one replaces")
        ] = None,
        mode: Annotated[
            Literal["auto", "new"],
            Field(description="auto: replace same subject, merge duplicates. new: always add"),
        ] = "auto",
        importance: Annotated[float, Field(ge=0, le=1)] = 0.5,
        confidence: Annotated[float, Field(ge=0, le=1)] = 0.8,
    ) -> dict:
        """Save or update a durable memory about the user. Secrets are rejected."""
        result = run(
            service.upsert,
            namespace,
            content,
            subject=subject,
            memory_id=id,
            supersedes=supersedes,
            mode=mode,
            importance=importance,
            confidence=confidence,
            provider=_client_name(ctx),
        )
        return result.to_dict()

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def memory_delete(ctx: Context, id: str) -> dict:
        """Permanently delete a memory. Only when the user asks for it."""
        return run(service.delete, id, provider=_client_name(ctx))

    assert set(Namespace.__args__) == set(NAMESPACES)
    return mcp
