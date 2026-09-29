"""Database connection and schema setup."""

from __future__ import annotations

from importlib import resources

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _configure(conn: psycopg.Connection) -> None:
    register_vector(conn)


def create_pool(database_url: str) -> ConnectionPool:
    # The vector type must exist before connections can register it.
    ensure_extension(database_url)
    return ConnectionPool(
        database_url,
        min_size=1,
        max_size=10,
        kwargs={"row_factory": dict_row, "autocommit": False},
        configure=_configure,
        open=True,
    )


def ensure_extension(database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")


def init_schema(pool: ConnectionPool, dimensions: int) -> None:
    sql = resources.files("memorybus").joinpath("schema.sql").read_text()
    with pool.connection() as conn:
        conn.execute(sql.replace("{dim}", str(int(dimensions))))
        row = conn.execute(
            "SELECT atttypmod AS dim FROM pg_attribute "
            "WHERE attrelid = 'memories'::regclass AND attname = 'embedding'"
        ).fetchone()
    if row and row["dim"] != dimensions:
        raise RuntimeError(
            f"memories.embedding has {row['dim']} dimensions but EMBEDDING_DIMENSIONS="
            f"{dimensions}. Changing dimensions needs a re-embedding migration."
        )
