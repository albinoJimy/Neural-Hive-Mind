"""Pytest configuration and fixtures for Architect Agent tests"""

import asyncio
import pytest
from unittest.mock import AsyncMock
from motor.motor_asyncio import AsyncIOMotorClient

from src.config.settings import get_settings


@pytest.fixture
def settings():
    """Get settings instance for tests"""
    return get_settings()


@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def mongo_client(settings):
    """Cliente MongoDB para testes."""
    client = AsyncIOMotorClient(settings.mongodb.url)

    yield client

    # Cleanup: drop test database
    await client.drop_database(settings.mongodb.database)
    client.close()


@pytest.fixture
async def mongo_database(mongo_client, settings):
    """Database instance for tests"""
    return mongo_client[settings.mongodb.database]


@pytest.fixture
def architecture_collection(mongo_database, settings):
    """Architecture plans collection for tests"""
    return mongo_database[settings.mongodb.collection_architecture]


@pytest.fixture
def validation_collection(mongo_database, settings):
    """Validation reports collection for tests"""
    return mongo_database[settings.mongodb.collection_validation]


@pytest.fixture
def evolution_collection(mongo_database, settings):
    """Evolution history collection for tests"""
    return mongo_database[settings.mongodb.collection_evolution]


@pytest.fixture
def mock_scout_client():
    """Mock do Scout Agent client."""
    mock = AsyncMock()
    mock.get_patterns.return_value = {"patterns": []}
    mock.get_insights.return_value = {"insights": []}
    mock.analyze_architecture.return_value = {
        "architecture_type": "microservices",
        "components": [],
        "patterns": [],
        "recommendations": [],
    }
    return mock


@pytest.fixture
def mock_llm_client():
    """Mock do LLM client."""
    mock = AsyncMock()
    mock.generate.return_value = """
    ```json
    {
      "architecture_type": "microservices",
      "components": [
        {"name": "api", "stack": "python/fastapi", "responsibility": "HTTP interface"}
      ],
      "patterns": ["repository", "circuit_breaker"],
      "rationale": "Test rationale for architecture"
    }
    ```
    """
    return mock


@pytest.fixture
def mock_opa_client():
    """Mock do OPA client."""
    mock = AsyncMock()
    mock.evaluate_policy.return_value = {"result": True, "reasons": []}
    return mock


@pytest.fixture
def sample_cognitive_plan():
    """Sample cognitive plan for testing"""
    return {
        "plan_id": "plan-test-001",
        "intent": {
            "action": "design",
            "subject": "user_management_api",
            "context": {"domain": "technical", "requirements": ["rest", "authentication", "crud"]},
        },
        "original_intent_text": "Design a user management API with REST endpoints",
        "specialists": ["technical", "architecture"],
        "created_at": "2026-03-27T10:00:00Z",
    }
