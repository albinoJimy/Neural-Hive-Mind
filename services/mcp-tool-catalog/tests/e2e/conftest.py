import asyncio

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from src.config.settings import Settings
from src.services.genetic_tool_selector import GeneticToolSelector
from src.services.tool_executor import ToolExecutor
from src.services.tool_registry import ToolRegistry


@pytest.fixture(scope="session")
async def test_mongodb():
    """MongoDB test instance."""
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["mcp_test"]
    yield db
    await client.drop_database("mcp_test")
    client.close()


@pytest.fixture(scope="session")
async def test_redis():
    """Redis test instance."""
    redis = Redis.from_url("redis://localhost:6379/1")
    yield redis
    await redis.flushdb()
    await redis.close()


@pytest.fixture
async def tool_registry(test_mongodb, test_redis):
    """Tool registry with test dependencies."""
    settings = Settings()
    registry = ToolRegistry(mongodb_client=test_mongodb, redis_client=test_redis, settings=settings)
    await registry.bootstrap_catalog()  # Load 87 tools
    return registry


@pytest.fixture
async def genetic_selector(tool_registry):
    """Genetic tool selector."""
    settings = Settings()
    return GeneticToolSelector(tool_registry, settings)


@pytest.fixture
async def tool_executor():
    """Tool executor with real adapters."""
    return ToolExecutor()
