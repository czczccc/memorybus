import os

import pytest

from memorybus.db import create_pool, init_schema
from memorybus.embeddings import HashEmbedder
from memorybus.service import MemoryService

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/memorybus_test"
)
DIM = 64


@pytest.fixture(scope="session")
def pool():
    pool = create_pool(TEST_DATABASE_URL)
    yield pool
    pool.close()


@pytest.fixture
def clean_db(pool):
    with pool.connection() as conn:
        conn.execute(
            "DROP TABLE IF EXISTS memory_events, memory_relations, memories, sources CASCADE"
        )
    init_schema(pool, DIM)
    return pool


@pytest.fixture
def service(clean_db):
    return MemoryService(clean_db, HashEmbedder(DIM))


@pytest.fixture
def keyword_service(clean_db):
    return MemoryService(clean_db, None)
