"""REST and MCP entry points share one store: a write through one is read through the other."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from conftest import DIM, TEST_DATABASE_URL
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import Client

from memorybus.app import create_app
from memorybus.config import Settings
from memorybus.embeddings import HashEmbedder
from memorybus.mcp_server import build_mcp, owner_only
from memorybus.rest import build_router

TOKEN = "test-token-123"
AUTH = {"Authorization": f"Bearer {TOKEN}", "X-MemoryBus-Client": "muse"}


@pytest.fixture
def settings():
    return Settings(database_url=TEST_DATABASE_URL, api_token=TOKEN, embedding_dimensions=DIM)


@pytest.fixture
def rest(settings, service):
    app = FastAPI()
    app.include_router(build_router(settings, service))
    return TestClient(app)


def call_tool(mcp, name, args):
    async def go():
        async with Client(mcp) as client:
            result = await client.call_tool(name, args)
            return result.structured_content

    return asyncio.run(go())


def test_rest_requires_token(rest):
    assert rest.get("/v1/memory/bootstrap").status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert rest.get("/v1/memory/bootstrap", headers=bad).status_code == 401


def test_rest_disabled_without_token(service):
    app = FastAPI()
    app.include_router(build_router(Settings(api_token=None), service))
    response = TestClient(app).get("/v1/memory/bootstrap", headers=AUTH)
    assert response.status_code == 503


def test_rest_crud(rest):
    body = {"namespace": "projects", "subject": "MemoryBus", "content": "User builds MemoryBus"}
    created = rest.post("/v1/memory", json=body, headers=AUTH).json()
    memory_id = created["memory"]["id"]
    assert created["action"] == "created"
    assert created["memory"]["source"]["provider"] == "rest:muse"

    assert rest.get(f"/v1/memory/{memory_id}", headers=AUTH).json()["subject"] == "MemoryBus"
    assert rest.get("/v1/memory?namespace=projects", headers=AUTH).json()[0]["id"] == memory_id
    assert rest.get("/v1/memory/search?q=MemoryBus", headers=AUTH).json()[0]["id"] == memory_id
    assert rest.get("/v1/memory/bootstrap", headers=AUTH).json()["active_projects"]

    updated = rest.put(
        f"/v1/memory/{memory_id}",
        json={**body, "content": "User builds MemoryBus v0.1"},
        headers=AUTH,
    ).json()
    assert updated["action"] == "updated"

    assert "## projects" in rest.get("/v1/memory/export?format=md", headers=AUTH).text
    assert rest.get("/v1/memory/events", headers=AUTH).json()[0]["provider"] == "rest:muse"
    assert rest.delete(f"/v1/memory/{memory_id}", headers=AUTH).status_code == 200
    assert rest.get(f"/v1/memory/{memory_id}", headers=AUTH).status_code == 404


def test_rest_rejects_secret(rest):
    body = {"namespace": "environment", "content": "password: correct-horse-battery"}
    response = rest.post("/v1/memory", json=body, headers=AUTH)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "secret_detected"


def test_mcp_tools_listed(settings, service):
    mcp = build_mcp(settings, service)

    async def go():
        async with Client(mcp) as client:
            return {t.name for t in await client.list_tools()}

    assert asyncio.run(go()) == {
        "memory_bootstrap",
        "memory_search",
        "memory_get",
        "memory_list",
        "memory_recent",
        "memory_upsert",
        "memory_delete",
    }


def test_write_in_one_client_read_in_the_other(settings, service, rest):
    """PRD §29 items 5 and 6, with ChatGPT on MCP and Muse on REST."""
    mcp = build_mcp(settings, service)
    call_tool(
        mcp,
        "memory_upsert",
        {
            "namespace": "current_state",
            "subject": "primary project",
            "content": "Primary project = JobAgent Studio",
        },
    )
    packet = rest.get("/v1/memory/bootstrap", headers=AUTH).json()
    assert packet["current_state"][0]["content"] == "Primary project = JobAgent Studio"

    rest.post(
        "/v1/memory",
        headers=AUTH,
        json={
            "namespace": "current_state",
            "subject": "primary project",
            "content": "Primary project = MemoryBus",
        },
    )
    found = call_tool(mcp, "memory_search", {"query": "primary project"})
    items = found["result"] if isinstance(found, dict) and "result" in found else found
    assert [m["content"] for m in items] == ["Primary project = MemoryBus"]


def test_mcp_secret_is_tool_error(settings, service):
    mcp = build_mcp(settings, service)

    async def go():
        async with Client(mcp) as client:
            return await client.call_tool(
                "memory_upsert",
                {"namespace": "environment", "content": "key sk-abcdefghijklmnopqrstuvwxyz0123"},
                raise_on_error=False,
            )

    result = asyncio.run(go())
    assert result.is_error
    assert "secret" in json.dumps([c.model_dump() for c in result.content])


def test_owner_only_check():
    check = owner_only(["c1463693519-rgb"])

    def ctx(login):
        token = SimpleNamespace(claims={"login": login}) if login else None
        return SimpleNamespace(token=token, component=None)

    assert check(ctx("C1463693519-rgb"))
    assert not check(ctx("someone-else"))
    assert not check(ctx(None))


def test_app_with_oauth(clean_db):
    settings = Settings(
        database_url=TEST_DATABASE_URL,
        public_base_url="https://memorybus.example.com",
        api_token=TOKEN,
        github_client_id="Iv1.test",
        github_client_secret="test-secret",
        allowed_github_logins=["c1463693519-rgb"],
        jwt_signing_key="test-signing-key-test-signing-key",
        embedding_dimensions=DIM,
    )
    app = create_app(settings, embedder=HashEmbedder(DIM))
    with TestClient(app, base_url="https://memorybus.example.com") as client:
        assert client.get("/healthz").json() == {"ok": True, "embeddings": True}
        meta = client.get("/.well-known/oauth-authorization-server")
        assert meta.status_code == 200
        assert meta.json()["authorization_endpoint"].startswith("https://memorybus.example.com")
        resource = client.get("/.well-known/oauth-protected-resource/mcp")
        assert resource.status_code == 200
        unauthenticated = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert unauthenticated.status_code == 401
        assert client.get("/v1/memory/bootstrap", headers=AUTH).status_code == 200


def test_public_mcp_requires_oauth(service):
    settings = Settings(public_base_url="https://memorybus.example.com", api_token=TOKEN)
    with pytest.raises(RuntimeError, match="without OAuth"):
        build_mcp(settings, service)
