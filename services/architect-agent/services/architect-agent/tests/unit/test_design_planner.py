"""Testes unitários para DesignPlanner."""

import pytest
from unittest.mock import AsyncMock

from src.models.architecture import ArchitectureType, Pattern
from src.planners.design_planner import DesignPlanner


@pytest.fixture
def mock_llm_client():
    """Mock do LLMClient para testes."""
    mock = AsyncMock()
    mock.generate.return_value = """{
      "architecture_type": "microservices",
      "components": [
        {"name": "api", "stack": "python/fastapi", "replicas": 3},
        {"name": "database", "stack": "postgresql", "replicas": 1}
      ],
      "patterns": ["repository", "cqrs"],
      "rationale": "Test rationale"
    }"""
    return mock


@pytest.mark.asyncio
async def test_design_planner_generates_plan(mock_llm_client):
    """Testa que DesignPlanner gera ArchitecturePlan."""
    # Patch o LLMClient para usar o mock
    from src.planners import design_planner

    original_llm_client = design_planner.LLMClient
    design_planner.LLMClient = lambda: mock_llm_client

    try:
        planner = DesignPlanner()

        requirements = {
            "intent": "create user management microservice",
            "scale": "high",
            "consistency": "strong",
            "latency_p99_ms": 200,
        }

        plan = await planner.plan(requirements)

        assert plan.plan_id.startswith("arch-")
        assert len(plan.plan_id) >= 12  # "arch-" + 8+ caracteres hex
        assert plan.architecture_type == ArchitectureType.MICROSERVICES
        assert len(plan.components) > 0
        assert len(plan.patterns) > 0
        assert plan.rationale != ""
        assert plan.components[0].name == "api"
        assert plan.components[0].stack == "python/fastapi"
        assert Pattern.REPOSITORY in plan.patterns
    finally:
        # Restore original
        design_planner.LLMClient = original_llm_client


@pytest.mark.asyncio
async def test_design_planner_refines_plan(mock_llm_client):
    """Testa que DesignPlanner refina plano existente."""
    from src.planners import design_planner

    original_llm_client = design_planner.LLMClient
    design_planner.LLMClient = lambda: mock_llm_client

    try:
        planner = DesignPlanner()

        feedback = {
            "new_intent": "convert to serverless",
            "feedback": "Need better cold start performance",
        }

        refined = await planner.refine("arch-123", feedback)

        assert refined.plan_id.startswith("arch-")
        assert refined.architecture_type == ArchitectureType.MICROSERVICES
    finally:
        design_planner.LLMClient = original_llm_client


@pytest.mark.asyncio
async def test_design_planner_parse_llm_response_with_markdown():
    """Testa parsing de resposta LLM com markdown code blocks."""
    planner = DesignPlanner()

    response = """
    ```json
    {
      "architecture_type": "microservices",
      "components": [
        {"name": "api", "stack": "python/fastapi", "replicas": 3}
      ],
      "patterns": ["repository", "cqrs"],
      "rationale": "Test rationale"
    }
    ```
    """

    result = planner._parse_llm_response(response)

    assert result["architecture_type"] == ArchitectureType.MICROSERVICES
    assert len(result["components"]) == 1
    assert result["components"][0].name == "api"
    assert result["components"][0].stack == "python/fastapi"
    assert result["components"][0].replicas == 3
    assert Pattern.REPOSITORY in result["patterns"]
    assert Pattern.CQRS in result["patterns"]
    assert result["rationale"] == "Test rationale"


@pytest.mark.asyncio
async def test_design_planner_parse_llm_response_without_markdown():
    """Testa parsing de resposta LLM sem markdown."""
    planner = DesignPlanner()

    response = """{
      "architecture_type": "monolith",
      "components": [
        {"name": "app", "stack": "python/fastapi"}
      ],
      "patterns": ["repository"],
      "rationale": "Simple monolith"
    }"""

    result = planner._parse_llm_response(response)

    assert result["architecture_type"] == ArchitectureType.MONOLITH
    assert len(result["components"]) == 1
    assert result["components"][0].name == "app"
    assert Pattern.REPOSITORY in result["patterns"]


@pytest.mark.asyncio
async def test_design_planner_parse_invalid_json():
    """Testa fallback quando JSON é inválido."""
    planner = DesignPlanner()

    response = "This is not valid JSON at all"

    result = planner._parse_llm_response(response)

    # Deve retornar fallback MONOLITH
    assert result["architecture_type"] == ArchitectureType.MONOLITH
    assert len(result["components"]) == 1
    assert result["components"][0].name == "app"
    assert Pattern.REPOSITORY in result["patterns"]
    assert "Error parsing LLM response" in result["rationale"]


@pytest.mark.asyncio
async def test_design_planner_parse_with_string_components():
    """Testa parsing com componentes como strings."""
    planner = DesignPlanner()

    response = """{
      "architecture_type": "microservices",
      "components": ["api", "database"],
      "patterns": ["repository"],
      "rationale": "String components"
    }"""

    result = planner._parse_llm_response(response)

    assert len(result["components"]) == 2
    # Componentes string devem ter stack padrão
    assert result["components"][0].name == "api"
    assert result["components"][0].stack == "python/fastapi"
    assert result["components"][1].name == "database"


@pytest.mark.asyncio
async def test_design_planner_parse_with_invalid_pattern():
    """Testa que padrões inválidos são ignorados."""
    planner = DesignPlanner()

    response = """{
      "architecture_type": "microservices",
      "components": [{"name": "api", "stack": "python/fastapi"}],
      "patterns": ["repository", "invalid_pattern", "cqrs"],
      "rationale": "Test"
    }"""

    result = planner._parse_llm_response(response)

    # Apenas padrões válidos devem estar presentes
    assert Pattern.REPOSITORY in result["patterns"]
    assert Pattern.CQRS in result["patterns"]
    # Padrão inválido não deve estar na lista
    assert all(isinstance(p, Pattern) for p in result["patterns"])


@pytest.mark.asyncio
async def test_design_planner_with_cognitive_plan_id():
    """Testa que cognitive_plan_id é propagado."""
    from src.planners import design_planner

    # Criar mock real
    from unittest.mock import AsyncMock

    mock_llm = AsyncMock()
    mock_llm.generate.return_value = """{
      "architecture_type": "monolith",
      "components": [{"name": "app", "stack": "python/fastapi"}],
      "patterns": ["repository"],
      "rationale": "Test"
    }"""

    original_llm_client = design_planner.LLMClient
    design_planner.LLMClient = lambda: mock_llm

    try:
        planner = DesignPlanner()

        requirements = {
            "intent": "test",
            "cognitive_plan_id": "cp-test-123",
        }

        plan = await planner.plan(requirements)

        assert plan.cognitive_plan_id == "cp-test-123"
    finally:
        design_planner.LLMClient = original_llm_client
