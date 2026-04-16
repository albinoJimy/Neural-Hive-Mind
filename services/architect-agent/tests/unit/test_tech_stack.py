"""Unit tests for TechStackRecommender."""

import pytest
from src.recommenders.tech_stack import TechStackRecommender


@pytest.mark.asyncio
async def test_recommend_tech_stack_for_api():
    """Testa recomendação de stack para API REST."""

    recommender = TechStackRecommender()

    requirements = "API REST para gestão de tarefas com alta concorrência"
    constraints = [{"type": "language", "value": "Python"}]

    result = await recommender.recommend(requirements, constraints)

    assert len(result.choices) > 0
    assert any(c.category == "backend" for c in result.choices)
    assert result.constraints_satisfied == ["language: Python"]


@pytest.mark.asyncio
async def test_recommend_with_postgresql_preference():
    """Testa recomendação com preferência de PostgreSQL."""

    recommender = TechStackRecommender()

    requirements = "Sistema transacional com dados relacionais"
    constraints = [{"type": "database", "value": "PostgreSQL"}]

    result = await recommender.recommend(requirements, constraints)

    db_choice = next((c for c in result.choices if c.category == "database"), None)
    assert db_choice is not None
    assert "PostgreSQL" in db_choice.name


@pytest.mark.asyncio
async def test_recommend_returns_confidence_score():
    """Testa que recomendação retorna score de confiança."""

    recommender = TechStackRecommender()

    requirements = "Sistema simples de blog"
    constraints = []

    result = await recommender.recommend(requirements, constraints)

    assert 0.0 <= result.confidence_score <= 1.0
