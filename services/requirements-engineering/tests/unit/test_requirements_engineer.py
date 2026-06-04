"""Testes unitários para RequirementsEngineer."""

from unittest.mock import AsyncMock, Mock

import pytest
from src.models.requirements import (
    Requirement,
    RequirementPriority,
    RequirementType,
)
from src.services.requirements_engineer import RequirementsEngineer


@pytest.fixture()
def mock_llm_response():
    """Fixture para mock LLM response."""
    mock = Mock()
    mock.choices = [Mock()]
    mock.choices[0].message = {
        "content": """
[
  {
    "id": "REQ-001",
    "title": "Autenticação de utilizadores",
    "description": "O sistema deve permitir autenticação via email e senha",
    "priority": "high",
    "type": "functional",
    "rationale": "Necessário para proteger o acesso ao sistema"
  },
  {
    "id": "REQ-002",
    "title": "Disponibilidade 99.9%",
    "description": "O sistema deve estar disponível 99.9% do tempo",
    "priority": "high",
    "type": "non_functional",
    "rationale": "Requisito de SLA"
  }
]
""",
        "role": "assistant",
    }
    return mock


@pytest.fixture()
def engineer(mock_llm_response):
    """Fixture para RequirementsEngineer."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=mock_llm_response)
    return RequirementsEngineer(llm_client=mock_client)


@pytest.mark.asyncio()
async def test_generate_requirements_from_cognitive_plan(engineer):
    """Testa geração de requisitos a partir de CognitivePlan."""
    # Arrange
    cognitive_plan_text = "Criar um sistema de gestão de utilizadores com autenticação"

    # Act
    requirements_set = await engineer.generate_from_cognitive_plan(
        plan_id="CP-001", plan_text=cognitive_plan_text
    )

    # Assert
    assert hasattr(requirements_set, "requirements")
    assert hasattr(requirements_set, "cognitive_plan_id")
    assert requirements_set.cognitive_plan_id == "CP-001"
    assert len(requirements_set.requirements) > 0
    assert isinstance(requirements_set.requirements[0], Requirement)


@pytest.mark.asyncio()
async def test_generate_requirements_includes_functional_and_non_functional(engineer):
    """Testa que gera ambos tipos de requisitos."""
    # Arrange
    cognitive_plan_text = "Sistema de e-commerce com alta disponibilidade"

    # Act
    requirements_set = await engineer.generate_from_cognitive_plan(
        plan_id="CP-002", plan_text=cognitive_plan_text
    )

    # Assert
    functional = [
        r for r in requirements_set.requirements if r.requirement_type == RequirementType.FUNCTIONAL
    ]
    non_functional = [
        r
        for r in requirements_set.requirements
        if r.requirement_type == RequirementType.NON_FUNCTIONAL
    ]

    assert len(functional) > 0, "Deve gerar requisitos funcionais"
    assert len(non_functional) > 0, "Deve gerar requisitos não-funcionais"


@pytest.mark.asyncio()
async def test_prioritize_requirements_correctly(engineer):
    """Testa priorização correta de requisitos."""
    # Arrange
    requirements = [
        Requirement(
            id="REQ-001",
            title="Login",
            description="Login de usuário com pelo menos 10 caracteres",
            priority=RequirementPriority.HIGH,
        ),
        Requirement(
            id="REQ-002",
            title="Logout",
            description="Logout de usuário do sistema",
            priority=RequirementPriority.MEDIUM,
        ),
    ]

    # Act
    prioritized = await engineer.prioritize_requirements(requirements)

    # Assert
    assert prioritized[0].priority == RequirementPriority.HIGH


@pytest.mark.asyncio()
async def test_identify_dependencies(engineer):
    """Testa identificação de dependências entre requisitos."""
    # Arrange
    requirements = [
        Requirement(id="REQ-001", title="Criar usuário", description="Criar usuário no sistema"),
        Requirement(
            id="REQ-002", title="Autenticar usuário", description="Autenticar usuário criado"
        ),
    ]

    # Mock da resposta do LLM para análise de dependências
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = {
        "content": """[
  {"id": "REQ-001", "dependencies": [], "conflicts": []},
  {"id": "REQ-002", "dependencies": ["REQ-001"], "conflicts": []}
]""",
        "role": "assistant",
    }
    engineer._llm_client.generate = AsyncMock(return_value=mock_response)

    # Act
    analyzed = await engineer.analyze_dependencies(requirements)

    # Assert
    assert "REQ-001" in analyzed[1].dependencies, "REQ-002 deve depender de REQ-001"
