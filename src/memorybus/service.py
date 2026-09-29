"""Memory Core: the protocol-independent logic behind both MCP and REST entry points."""

from __future__ import annotations

import json
import math
import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .embeddings import Embedder
from .secret_filter import find_secrets

NAMESPACES = (
    "profile",
    "preferences",
    "projects",
    "decisions",
    "environment",
    "goals",
    "current_state",
    "open_loops",
)

# Section name in the bootstrap packet -> (namespace, max items)
BOOTSTRAP_SECTIONS: list[tuple[str, str, int]] = [
    ("profile", "profile", 10),
    ("preferences", "preferences", 15),
    ("environment", "environment", 10),
    ("active_projects", "projects", 10),
    ("current_state", "current_state", 10),
    ("recent_decisions", "decisions", 10),
    ("goals", "goals", 8),
    ("open_loops", "open_loops", 10),
]

DEFAULT_BOOTSTRAP_TOKENS = 2000
FRESHNESS_HALF_LIFE_DAYS = 180
DUPLICATE_SIMILARITY = 0.97

_COLUMNS = (
    "id, namespace, subject, content, source_provider, source_conversation_id, confidence, "
    "importance, status, created_at, updated_at, expires_at, supersedes, metadata"
)
_ACTIVE = "status = 'active' AND (expires_at IS NULL OR expires_at > now())"


class MemoryBusError(Exception):
    """Base error for invalid memory operations."""


class SecretRejected(MemoryBusError):
    def __init__(self, kinds: list[str]):
        self.kinds = kinds
        super().__init__(f"Rejected: content looks like it contains secrets ({', '.join(kinds)})")


class NotFound(MemoryBusError):
    pass


@dataclass
class UpsertResult:
    action: Literal["created", "updated", "merged", "superseded"]
    memory: dict[str, Any]
    superseded: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "memory": self.memory, "superseded": self.superseded}


def new_id() -> str:
    return f"mem_{int(time.time() * 1000):011x}{secrets.token_hex(4)}"


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in ("embedding", "score", "similarity"):
            continue
        out[key] = value.isoformat() if isinstance(value, datetime) else value
    out["source"] = {
        "provider": out.pop("source_provider", None),
        "conversation_id": out.pop("source_conversation_id", None),
    }
    return out


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _query_terms(query: str) -> list[str]:
    """ASCII words, plus CJK runs split into bigrams, for keyword matching."""
    terms: list[str] = []
    for match in re.finditer(r"[A-Za-z0-9_.+#-]{2,}|[^\x00-\x7f\s\W]+", query):
        token = match.group().lower()
        if token.isascii() or len(token) == 1:
            terms.append(token)
        else:
            terms.extend(token[i : i + 2] for i in range(len(token) - 1))
    return list(dict.fromkeys(terms))


def _estimate_tokens(text: str) -> int:
    cjk = sum(1 for ch in text if ord(ch) > 0x2E80)
    return cjk + (len(text) - cjk) // 4 + 1


def _freshness(updated_at: datetime) -> float:
    age_days = max((datetime.now(UTC) - updated_at).total_seconds() / 86400, 0)
    return 0.5 + 0.5 * math.exp(-age_days * math.log(2) / FRESHNESS_HALF_LIFE_DAYS)


def rank_score(relevance: float, row: dict[str, Any]) -> float:
    """PRD §13: relevance × importance × freshness × confidence (softened to 0.5–1 each)."""
    return (
        relevance
        * (0.5 + 0.5 * row["importance"])
        * _freshness(row["updated_at"])
        * (0.5 + 0.5 * row["confidence"])
    )


class MemoryService:
    def __init__(self, pool: ConnectionPool, embedder: Embedder | None = None):
        self.pool = pool
        self.embedder = embedder

    # ------------------------------------------------------------------ helpers

    def _embed(self, text: str) -> list[float] | None:
        if self.embedder is None:
            return None
        return self.embedder.embed([text])[0]

    def _log(self, conn, provider: str, action: str, ids: list[str], detail: dict) -> None:
        conn.execute(
            "INSERT INTO sources (provider) VALUES (%s) "
            "ON CONFLICT (provider) DO UPDATE SET last_seen = now()",
            (provider,),
        )
        conn.execute(
            "INSERT INTO memory_events (provider, action, memory_ids, detail) "
            "VALUES (%s, %s, %s, %s)",
            (provider, action, ids, Jsonb(detail)),
        )

    @staticmethod
    def _check_namespace(namespace: str) -> None:
        if namespace not in NAMESPACES:
            raise MemoryBusError(
                f"Unknown namespace {namespace!r}; use one of {', '.join(NAMESPACES)}"
            )

    # ------------------------------------------------------------------ reads

    def get(self, memory_id: str, provider: str = "unknown") -> dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM memories WHERE id = %s", (memory_id,)
            ).fetchone()
            if row is None:
                raise NotFound(f"No memory with id {memory_id}")
            self._log(conn, provider, "GET", [memory_id], {})
        return _serialize(row)

    def list(
        self,
        namespace: str | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        provider: str = "unknown",
    ) -> list[dict[str, Any]]:
        if namespace:
            self._check_namespace(namespace)
        where = ["TRUE" if include_inactive else _ACTIVE]
        params: list[Any] = []
        if namespace:
            where.append("namespace = %s")
            params.append(namespace)
        params.append(max(1, min(limit, 500)))
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM memories WHERE {' AND '.join(where)} "
                "ORDER BY importance DESC, updated_at DESC LIMIT %s",
                params,
            ).fetchall()
            self._log(conn, provider, "LIST", [r["id"] for r in rows], {"namespace": namespace})
        return [_serialize(r) for r in rows]

    def recent(self, limit: int = 20, provider: str = "unknown") -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM memories ORDER BY updated_at DESC LIMIT %s",
                (max(1, min(limit, 100)),),
            ).fetchall()
            self._log(conn, provider, "RECENT", [r["id"] for r in rows], {})
        return [_serialize(r) for r in rows]

    def bootstrap(
        self, max_tokens: int = DEFAULT_BOOTSTRAP_TOKENS, provider: str = "unknown"
    ) -> dict[str, Any]:
        """Memory Packet for a new conversation, capped at roughly ``max_tokens`` (PRD §12)."""
        packet: dict[str, Any] = {section: [] for section, _, _ in BOOTSTRAP_SECTIONS}
        budget = max(200, max_tokens)
        returned: list[str] = []
        with self.pool.connection() as conn:
            per_section = {
                section: conn.execute(
                    f"SELECT id, subject, content, importance, updated_at FROM memories "
                    f"WHERE namespace = %s AND {_ACTIVE} "
                    + (
                        "ORDER BY updated_at DESC LIMIT %s"
                        if namespace == "decisions"
                        else "ORDER BY importance DESC, updated_at DESC LIMIT %s"
                    ),
                    (namespace, limit),
                ).fetchall()
                for section, namespace, limit in BOOTSTRAP_SECTIONS
            }
            # Round-robin across sections so one busy namespace can't starve the others.
            depth = 0
            while budget > 0 and any(len(rows) > depth for rows in per_section.values()):
                for section, rows in per_section.items():
                    if depth >= len(rows):
                        continue
                    row = rows[depth]
                    item = {"id": row["id"], "subject": row["subject"], "content": row["content"]}
                    cost = _estimate_tokens(json.dumps(item, ensure_ascii=False))
                    if cost > budget:
                        continue
                    budget -= cost
                    packet[section].append(item)
                    returned.append(row["id"])
                depth += 1
            self._log(conn, provider, "BOOTSTRAP", returned, {"max_tokens": max_tokens})
        packet["generated_at"] = datetime.now(UTC).isoformat()
        return packet

    def search(
        self,
        query: str,
        limit: int = 10,
        namespace: str | None = None,
        include_inactive: bool = False,
        provider: str = "unknown",
    ) -> list[dict[str, Any]]:
        if namespace:
            self._check_namespace(namespace)
        limit = max(1, min(limit, 50))
        where = ["TRUE" if include_inactive else _ACTIVE]
        params: list[Any] = []
        if namespace:
            where.append("namespace = %s")
            params.append(namespace)
        where_sql = " AND ".join(where)

        candidates: dict[str, dict[str, Any]] = {}
        relevance: dict[str, float] = {}
        vector = self._embed(query)
        terms = _query_terms(query)

        with self.pool.connection() as conn:
            if vector is not None:
                rows = conn.execute(
                    f"SELECT {_COLUMNS}, 1 - (embedding <=> %s::vector) AS similarity "
                    f"FROM memories WHERE embedding IS NOT NULL AND {where_sql} "
                    "ORDER BY embedding <=> %s::vector LIMIT 50",
                    [vector, *params, vector],
                ).fetchall()
                for row in rows:
                    candidates[row["id"]] = row
                    relevance[row["id"]] = max(float(row["similarity"]), 0.0)
            if terms:
                patterns = [f"%{t}%" for t in terms]
                rows = conn.execute(
                    f"SELECT {_COLUMNS} FROM memories WHERE {where_sql} AND "
                    "(content ILIKE ANY(%s) OR subject ILIKE ANY(%s)) "
                    "ORDER BY updated_at DESC LIMIT 100",
                    [*params, patterns, patterns],
                ).fetchall()
                for row in rows:
                    haystack = f"{row['subject']} {row['content']}".lower()
                    hit = sum(1 for t in terms if t in haystack) / len(terms)
                    candidates.setdefault(row["id"], row)
                    # Keyword hits blend with (never replace) semantic similarity.
                    relevance[row["id"]] = max(relevance.get(row["id"], 0.0), 0.3 + 0.6 * hit)

            ranked = sorted(
                candidates.values(),
                key=lambda r: rank_score(relevance[r["id"]], r),
                reverse=True,
            )[:limit]
            results = []
            for row in ranked:
                item = _serialize(row)
                item["score"] = round(rank_score(relevance[row["id"]], row), 4)
                results.append(item)
            self._log(conn, provider, "SEARCH", [r["id"] for r in results], {"query": query})
        return results

    # ------------------------------------------------------------------ writes

    def upsert(
        self,
        namespace: str,
        content: str,
        subject: str = "",
        memory_id: str | None = None,
        supersedes: str | None = None,
        mode: Literal["auto", "new"] = "auto",
        confidence: float = 0.8,
        importance: float = 0.5,
        expires_at: str | None = None,
        metadata: dict[str, Any] | None = None,
        conversation_id: str | None = None,
        provider: str = "unknown",
    ) -> UpsertResult:
        """Create or update a memory, resolving conflicts (PRD §7, §15).

        - ``memory_id`` given: update that memory in place.
        - ``supersedes`` given: create a new memory and mark that one superseded.
        - ``mode="auto"``: an active memory with the same namespace and subject is
          superseded; identical content (or a near-duplicate) is merged instead.
        - ``mode="new"``: always add alongside existing memories.
        """
        self._check_namespace(namespace)
        content = content.strip()
        subject = subject.strip()
        metadata = metadata or {}
        if not content:
            raise MemoryBusError("content must not be empty")
        kinds = find_secrets(" ".join([subject, content, json.dumps(metadata, ensure_ascii=False)]))
        if kinds:
            with self.pool.connection() as conn:
                self._log(conn, provider, "REJECT", [], {"reason": "secret", "kinds": kinds})
            raise SecretRejected(kinds)
        confidence = min(max(float(confidence), 0.0), 1.0)
        importance = min(max(float(importance), 0.0), 1.0)
        vector = self._embed(f"{subject}: {content}" if subject else content)

        with self.pool.connection() as conn:
            if memory_id:
                return self._update_in_place(
                    conn,
                    memory_id,
                    namespace,
                    subject,
                    content,
                    confidence,
                    importance,
                    expires_at,
                    metadata,
                    vector,
                    provider,
                )

            to_supersede: list[dict[str, Any]] = []
            if supersedes:
                old = conn.execute(
                    f"SELECT {_COLUMNS} FROM memories WHERE id = %s FOR UPDATE", (supersedes,)
                ).fetchone()
                if old is None:
                    raise NotFound(f"No memory with id {supersedes}")
                to_supersede.append(old)
            elif mode == "auto":
                duplicate = self._find_duplicate(conn, namespace, content, vector)
                if duplicate is not None:
                    merged = conn.execute(
                        "UPDATE memories SET updated_at = now(), "
                        "confidence = GREATEST(confidence, %s), "
                        "importance = GREATEST(importance, %s) "
                        f"WHERE id = %s RETURNING {_COLUMNS}",
                        (confidence, importance, duplicate["id"]),
                    ).fetchone()
                    self._log(conn, provider, "MERGE", [merged["id"]], {"content": content})
                    return UpsertResult("merged", _serialize(merged), [])
                if subject:
                    to_supersede = conn.execute(
                        f"SELECT {_COLUMNS} FROM memories WHERE namespace = %s "
                        f"AND lower(subject) = lower(%s) AND {_ACTIVE} FOR UPDATE",
                        (namespace, subject),
                    ).fetchall()

            new_memory_id = new_id()
            row = conn.execute(
                "INSERT INTO memories (id, namespace, subject, content, source_provider, "
                "source_conversation_id, confidence, importance, expires_at, supersedes, "
                f"metadata, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                f"RETURNING {_COLUMNS}",
                (
                    new_memory_id,
                    namespace,
                    subject,
                    content,
                    provider,
                    conversation_id,
                    confidence,
                    importance,
                    expires_at,
                    to_supersede[0]["id"] if to_supersede else None,
                    Jsonb(metadata),
                    vector,
                ),
            ).fetchone()
            for old in to_supersede:
                conn.execute(
                    "UPDATE memories SET status = 'superseded', updated_at = now() WHERE id = %s",
                    (old["id"],),
                )
                conn.execute(
                    "INSERT INTO memory_relations (from_id, to_id, relation) "
                    "VALUES (%s, %s, 'supersedes') ON CONFLICT DO NOTHING",
                    (new_memory_id, old["id"]),
                )
            superseded = [{**_serialize(old), "status": "superseded"} for old in to_supersede]
            action = "superseded" if to_supersede else "created"
            self._log(
                conn,
                provider,
                "WRITE",
                [new_memory_id] + [o["id"] for o in to_supersede],
                {
                    "action": action,
                    "namespace": namespace,
                    "subject": subject,
                    "to": content,
                    "from": [o["content"] for o in to_supersede],
                },
            )
        return UpsertResult(action, _serialize(row), superseded)

    def _find_duplicate(self, conn, namespace: str, content: str, vector) -> dict | None:
        rows = conn.execute(
            f"SELECT id, content FROM memories WHERE namespace = %s AND {_ACTIVE}",
            (namespace,),
        ).fetchall()
        target = _normalize(content)
        for row in rows:
            if _normalize(row["content"]) == target:
                return row
        if vector is None:
            return None
        return conn.execute(
            f"SELECT id FROM memories WHERE namespace = %s AND {_ACTIVE} "
            "AND embedding IS NOT NULL AND 1 - (embedding <=> %s::vector) >= %s "
            "ORDER BY embedding <=> %s::vector LIMIT 1",
            (namespace, vector, DUPLICATE_SIMILARITY, vector),
        ).fetchone()

    def _update_in_place(
        self,
        conn,
        memory_id,
        namespace,
        subject,
        content,
        confidence,
        importance,
        expires_at,
        metadata,
        vector,
        provider,
    ) -> UpsertResult:
        old = conn.execute(
            f"SELECT {_COLUMNS} FROM memories WHERE id = %s FOR UPDATE", (memory_id,)
        ).fetchone()
        if old is None:
            raise NotFound(f"No memory with id {memory_id}")
        row = conn.execute(
            "UPDATE memories SET namespace = %s, subject = %s, content = %s, confidence = %s, "
            "importance = %s, expires_at = %s, metadata = %s, embedding = %s, "
            f"updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
            (
                namespace,
                subject,
                content,
                confidence,
                importance,
                expires_at,
                Jsonb(metadata),
                vector,
                memory_id,
            ),
        ).fetchone()
        self._log(
            conn,
            provider,
            "WRITE",
            [memory_id],
            {"action": "updated", "subject": subject, "from": old["content"], "to": content},
        )
        return UpsertResult("updated", _serialize(row), [])

    def delete(self, memory_id: str, provider: str = "unknown") -> dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"DELETE FROM memories WHERE id = %s RETURNING {_COLUMNS}", (memory_id,)
            ).fetchone()
            if row is None:
                raise NotFound(f"No memory with id {memory_id}")
            self._log(
                conn,
                provider,
                "DELETE",
                [memory_id],
                {
                    "namespace": row["namespace"],
                    "subject": row["subject"],
                    "content": row["content"],
                },
            )
        return _serialize(row)

    # ------------------------------------------------------------------ export

    def events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, at, provider, action, memory_ids, detail FROM memory_events "
                "ORDER BY id DESC LIMIT %s",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [{**r, "at": r["at"].isoformat()} for r in rows]

    def export_json(self) -> dict[str, Any]:
        with self.pool.connection() as conn:
            memories = conn.execute(
                f"SELECT {_COLUMNS} FROM memories ORDER BY namespace, created_at"
            ).fetchall()
            relations = conn.execute(
                "SELECT from_id, to_id, relation, created_at FROM memory_relations"
            ).fetchall()
        return {
            "format": "memorybus.export.v1",
            "exported_at": datetime.now(UTC).isoformat(),
            "memories": [_serialize(m) for m in memories],
            "relations": [{**r, "created_at": r["created_at"].isoformat()} for r in relations],
        }

    def export_markdown(self) -> str:
        data = self.export_json()
        lines = ["# MemoryBus export", "", f"Exported at {data['exported_at']}", ""]
        for namespace in NAMESPACES:
            items = [m for m in data["memories"] if m["namespace"] == namespace]
            if not items:
                continue
            lines += [f"## {namespace}", ""]
            for m in items:
                subject = f"**{m['subject']}**: " if m["subject"] else ""
                status = "" if m["status"] == "active" else f" _({m['status']})_"
                lines.append(f"- {subject}{m['content']}{status} `{m['id']}`")
            lines.append("")
        return "\n".join(lines)
