"""Unit tests for TechStackRecommender."""

from unittest.mock import AsyncMock, Mock

import pytest
from src.recommenders.tech_stack import TechStackRecommender

from neural_hive_llm import LLMProvider, LLMResponse


@pytest.fixture
def mock_llm_client():
    """Mock do cliente LLM usando neural_hive_llm."""
    client = Mock()
    client.start = AsyncMock()
    client.generate = AsyncMock(
        return_value=LLMResponse(
            text="""{
      "choices": [
        {"category": "backend", "name": "FastAPI", "version": "0.104", "rationale": "Async nativo"},
        {"category": "database", "name": "PostgreSQL", "version": "15", "rationale": "ACID compliant"}
      ],
      "constraints_satisfied": ["language: Python"],
      "constraints_violated": [],
      "confidence_score": 0.9,
      "estimated_complexity": "media",
      "estimated_cost": "$$"
    }""",
            prompt_tokens=50,
            completion_tokens=50,
            total_tokens=100,
            model="gpt-4",
            provider=LLMProvider.OPENAI,
            latency_ms=100,
        )
    )
    return client


@pytest.mark.asyncio
async def test_recommend_tech_stack_for_api(mock_llm_client):
    """Testa recomendação de stack para API REST."""

    recommender = TechStackRecommender(llm_client=mock_llm_client)

    requirements = "API REST para gestão de tarefas com alta concorrência"
    constraints = [{"type": "language", "value": "Python"}]

    result = await recommender.recommend(requirements, constraints)

    assert len(result.choices) == 2
    assert any(c.category == "backend" for c in result.choices)
    assert result.constraints_satisfied == ["language: Python"]


@pytest.mark.asyncio
async def test_recommend_with_postgresql_preference(mock_llm_client):
    """Testa recomendação com preferência de PostgreSQL."""

    recommender = TechStackRecommender(llm_client=mock_llm_client)

    requirements = "Sistema transacional com dados relacionais"
    constraints = [{"type": "database", "value": "PostgreSQL"}]

    result = await recommender.recommend(requirements, constraints)

    db_choice = next((c for c in result.choices if c.category == "database"), None)
    assert db_choice is not None
    assert "PostgreSQL" in db_choice.name


@pytest.mark.asyncio
async def test_recommend_returns_confidence_score(mock_llm_client):
    """Testa que recomendação retorna score de confiança."""

    recommender = TechStackRecommender(llm_client=mock_llm_client)

    requirements = "Sistema simples de blog"
    constraints = []

    result = await recommender.recommend(requirements, constraints)

    assert 0.0 <= result.confidence_score <= 1.0
