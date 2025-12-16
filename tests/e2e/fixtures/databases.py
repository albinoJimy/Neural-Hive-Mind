from typing import Dict

import asyncpg
import motor.motor_asyncio
import pytest
import redis.asyncio as redis


@pytest.fixture(scope="session")
async def mongodb_client(k8s_service_endpoints: Dict[str, str]):
    client = motor.motor_asyncio.AsyncIOMotorClient(k8s_service_endpoints["mongodb"])
    yield client
    client.close()


@pytest.fixture(scope="function")
async def test_mongodb_collections(mongodb_client) -> Dict[str, object]:
    # Use production collections to read real pipeline outputs
    db = mongodb_client["neural_hive_orchestration"]
    return {
        "cognitive_ledger": db["cognitive_ledger"],
        "execution_tickets": db["execution_tickets"],
        "workflows": db["workflows"],
        "strategic_decisions": db["strategic_decisions"],
    }


@pytest.fixture(scope="session")
async def redis_client(k8s_service_endpoints: Dict[str, str]):
    client = redis.Redis.from_url(f"redis://{k8s_service_endpoints['redis']}")
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture(scope="function")
async def test_redis_keys(redis_client):
    prefix = f"e2e:test:{uuid.uuid4().hex}:"
    yield prefix
    keys = await redis_client.keys(f"{prefix}*")
    if keys:
        await redis_client.delete(*keys)


@pytest.fixture(scope="session")
async def postgres_connection(k8s_service_endpoints: Dict[str, str]):
    conn = await asyncpg.connect(f"postgresql://temporal:temporal@{k8s_service_endpoints['temporal_db']}/temporal")
    try:
        yield conn
    finally:
        await conn.close()
