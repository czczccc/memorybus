from datetime import UTC, datetime, timedelta

import pytest

from memorybus.service import MemoryBusError, NotFound, SecretRejected, rank_score


def test_create_and_get(service):
    result = service.upsert(
        "projects", "User is building MemoryBus.", subject="MemoryBus", provider="chatgpt"
    )
    assert result.action == "created"
    memory = service.get(result.memory["id"])
    assert memory["content"] == "User is building MemoryBus."
    assert memory["source"] == {"provider": "chatgpt", "conversation_id": None}
    assert memory["status"] == "active"


def test_same_subject_supersedes(service):
    old = service.upsert(
        "current_state", "Primary project = JobAgent Studio", subject="primary project"
    )
    new = service.upsert("current_state", "Primary project = MemoryBus", subject="Primary Project")
    assert new.action == "superseded"
    assert [m["id"] for m in new.superseded] == [old.memory["id"]]
    assert new.memory["supersedes"] == old.memory["id"]
    assert service.get(old.memory["id"])["status"] == "superseded"
    active = service.list("current_state")
    assert [m["content"] for m in active] == ["Primary project = MemoryBus"]
    history = service.list("current_state", include_inactive=True)
    assert len(history) == 2


def test_duplicate_is_merged(service):
    first = service.upsert("environment", "User uses Windows + WSL.", importance=0.4)
    second = service.upsert("environment", "  user uses windows + wsl. ", importance=0.9)
    assert second.action == "merged"
    assert second.memory["id"] == first.memory["id"]
    assert second.memory["importance"] == pytest.approx(0.9)
    assert len(service.list("environment")) == 1


def test_mode_new_keeps_both(service):
    service.upsert("decisions", "JobAgent frontend = Next.js", subject="JobAgent")
    result = service.upsert(
        "decisions", "JobAgent database = PostgreSQL", subject="JobAgent", mode="new"
    )
    assert result.action == "created"
    assert len(service.list("decisions")) == 2


def test_explicit_supersedes(service):
    old = service.upsert("projects", "User is building JobAgent Studio.", subject="JobAgent")
    new = service.upsert(
        "projects",
        "User stopped working on JobAgent Studio.",
        subject="JobAgent status",
        supersedes=old.memory["id"],
    )
    assert new.action == "superseded"
    assert service.get(old.memory["id"])["status"] == "superseded"


def test_update_in_place(service):
    created = service.upsert("preferences", "Prefers pip", subject="python packaging")
    updated = service.upsert(
        "preferences", "Prefers uv", subject="python packaging", memory_id=created.memory["id"]
    )
    assert updated.action == "updated"
    assert service.get(created.memory["id"])["content"] == "Prefers uv"


def test_secret_rejected_and_logged(service):
    with pytest.raises(SecretRejected):
        service.upsert("environment", "OpenAI key sk-abcdefghijklmnopqrstuvwxyz0123")
    assert service.events()[0]["action"] == "REJECT"
    assert service.list(include_inactive=True) == []


def test_unknown_namespace(service):
    with pytest.raises(MemoryBusError):
        service.upsert("chat", "hello")


def test_delete(service):
    created = service.upsert("goals", "Build AI-native products.")
    service.delete(created.memory["id"])
    with pytest.raises(NotFound):
        service.get(created.memory["id"])
    assert service.events()[0]["action"] == "DELETE"


def test_semantic_search(service):
    service.upsert(
        "decisions", "JobAgent Studio database is PostgreSQL", subject="JobAgent Studio / database"
    )
    service.upsert("environment", "User develops on Windows with WSL Ubuntu")
    results = service.search("JobAgent database")
    assert results[0]["subject"] == "JobAgent Studio / database"
    assert "score" in results[0]


def test_keyword_search_without_embeddings(keyword_service):
    keyword_service.upsert(
        "decisions", "JobAgent Studio 数据库使用 PostgreSQL", subject="JobAgent Studio / database"
    )
    keyword_service.upsert("preferences", "Python 项目默认使用 uv")
    results = keyword_service.search("JobAgent 数据库")
    assert results[0]["subject"] == "JobAgent Studio / database"
    results = keyword_service.search("数据库")
    assert len(results) == 1


def test_search_hides_superseded(service):
    service.upsert("current_state", "Primary project = JobAgent", subject="primary project")
    service.upsert("current_state", "Primary project = MemoryBus", subject="primary project")
    contents = [m["content"] for m in service.search("primary project")]
    assert contents == ["Primary project = MemoryBus"]
    assert len(service.search("primary project", include_inactive=True)) == 2


def test_expired_memories_hidden(service):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    service.upsert("current_state", "Travelling this week", expires_at=past)
    assert service.list("current_state") == []


def test_bootstrap_packet(service):
    service.upsert("profile", "User's preferred name is Jay", subject="preferred name")
    service.upsert("projects", "User is building MemoryBus", subject="MemoryBus")
    service.upsert("open_loops", "Need to implement Muse connector")
    packet = service.bootstrap(provider="muse")
    assert packet["profile"][0]["content"] == "User's preferred name is Jay"
    assert packet["active_projects"][0]["subject"] == "MemoryBus"
    assert packet["open_loops"]
    assert set(packet) >= {"preferences", "recent_decisions", "current_state", "goals"}
    event = service.events()[0]
    assert event["action"] == "BOOTSTRAP" and event["provider"] == "muse"
    assert len(event["memory_ids"]) == 3


def test_bootstrap_respects_budget(service):
    for i in range(40):
        service.upsert("preferences", f"Preference number {i} " + "x" * 200, mode="new")
    service.upsert("profile", "User's preferred name is Jay")
    packet = service.bootstrap(max_tokens=300)
    assert len(packet["preferences"]) < 10
    assert packet["profile"], "round-robin keeps smaller sections"


def test_export(service):
    service.upsert("current_state", "Primary project = JobAgent", subject="primary project")
    service.upsert("current_state", "Primary project = MemoryBus", subject="primary project")
    data = service.export_json()
    assert len(data["memories"]) == 2
    assert data["relations"][0]["relation"] == "supersedes"
    md = service.export_markdown()
    assert "## current_state" in md and "(superseded)" in md


def test_rank_score_prefers_fresh_and_important():
    now = datetime.now(UTC)
    fresh = {"importance": 0.9, "confidence": 0.9, "updated_at": now}
    stale = {"importance": 0.9, "confidence": 0.9, "updated_at": now - timedelta(days=720)}
    minor = {"importance": 0.1, "confidence": 0.9, "updated_at": now}
    assert rank_score(0.8, fresh) > rank_score(0.8, stale)
    assert rank_score(0.8, fresh) > rank_score(0.8, minor)


class FailingEmbedder:
    dimensions = 64

    def embed(self, texts):
        raise TimeoutError("provider unreachable")


def test_embedding_failure_falls_back_to_keywords(clean_db):
    from memorybus.service import MemoryService

    service = MemoryService(clean_db, FailingEmbedder())
    created = service.upsert("projects", "User's primary project is MemoryBus", subject="MemoryBus")
    assert created.action == "created"
    results = service.search("MemoryBus")
    assert [m["id"] for m in results] == [created.memory["id"]]


def test_search_drops_unrelated_vector_hits(service):
    service.upsert("projects", "User's primary project is MemoryBus", subject="primary project")
    service.upsert("preferences", "User prefers uv for Python projects")
    results = service.search("MemoryBus")
    assert [m["subject"] for m in results] == ["primary project"]


def test_reembed_fills_missing_vectors(clean_db):
    from memorybus.embeddings import HashEmbedder
    from memorybus.service import MemoryService

    MemoryService(clean_db, None).upsert("preferences", "User prefers uv for Python projects")
    service = MemoryService(clean_db, HashEmbedder(64))
    assert service.reembed() == 1
    assert service.reembed() == 0
    assert service.reembed(all_memories=True) == 1
    assert service.events()[0]["action"] == "REEMBED"
    assert service.search("uv Python")[0]["content"] == "User prefers uv for Python projects"


def test_reembed_requires_embedder(keyword_service):
    with pytest.raises(MemoryBusError):
        keyword_service.reembed()
