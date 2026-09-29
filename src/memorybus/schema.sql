-- MemoryBus schema. {dim} is replaced with the configured embedding dimension.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sources (
    provider    TEXT PRIMARY KEY,
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memories (
    id                      TEXT PRIMARY KEY,
    namespace               TEXT NOT NULL,
    subject                 TEXT NOT NULL DEFAULT '',
    content                 TEXT NOT NULL,
    source_provider         TEXT NOT NULL DEFAULT 'unknown',
    source_conversation_id  TEXT,
    confidence              REAL NOT NULL DEFAULT 0.8 CHECK (confidence BETWEEN 0 AND 1),
    importance              REAL NOT NULL DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
    status                  TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'superseded', 'archived')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at              TIMESTAMPTZ,
    supersedes              TEXT REFERENCES memories(id) ON DELETE SET NULL,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding               vector({dim})
);

CREATE INDEX IF NOT EXISTS memories_ns_status_idx ON memories (namespace, status);
CREATE INDEX IF NOT EXISTS memories_subject_idx ON memories (namespace, lower(subject));
CREATE INDEX IF NOT EXISTS memories_updated_idx ON memories (updated_at DESC);
CREATE INDEX IF NOT EXISTS memories_embedding_idx
    ON memories USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS memory_relations (
    from_id     TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    to_id       TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relation    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (from_id, to_id, relation)
);

CREATE TABLE IF NOT EXISTS memory_events (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    provider    TEXT NOT NULL,
    action      TEXT NOT NULL,
    memory_ids  TEXT[] NOT NULL DEFAULT '{}',
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS memory_events_at_idx ON memory_events (at DESC);
