"""Testes unitários para ArchitectureRepository."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.models.architecture import ArchitecturePlan, ArchitectureType, Component, Pattern
from src.models.bounded_context import BoundedContext
from src.models.diagrams import Diagram, DiagramType
from src.models.tech_stack import TechChoice
from src.repositories.architecture_repository import ArchitectureRepository


@pytest.fixture
def mock_collection():
    """Fixture para collection MongoDB mockado."""
    collection = AsyncMock()
    collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test-id"))
    collection.find_one = AsyncMock(return_value=None)
    collection.create_index = AsyncMock()
    return collection


@pytest.fixture
def repository(mock_collection):
    """Fixture para ArchitectureRepository."""
    repo = ArchitectureRepository()
    repo.collection = mock_collection
    return repo


def test_validate_bounded_contexts_empty_list(repository):
    """Testa que bounded_contexts vazio lança ValueError."""
    plan = ArchitecturePlan(
        plan_id="test-1",
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[Component(name="api", stack="python")],
        patterns=[Pattern.API_GATEWAY],
        rationale="Test",
        bounded_contexts=[],  # Lista vazia
    )

    with pytest.raises(ValueError, match="bounded_contexts cannot be empty"):
        repository._validate_extended_fields(plan)


def test_validate_bounded_contexts_missing_name(repository):
    """Testa que bounded context sem nome lança ValueError."""
    ctx = BoundedContext(
        name="",  # Nome vazio
        description="Test",
        responsibilities=["test"],
        domain_models=["Model"],
    )

    plan = ArchitecturePlan(
        plan_id="test-2",
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[Component(name="api", stack="python")],
        patterns=[Pattern.API_GATEWAY],
        rationale="Test",
        bounded_contexts=[ctx],
    )

    with pytest.raises(ValueError, match="bounded_contexts\\[0\\].name cannot be empty"):
        repository._validate_extended_fields(plan)


def test_validate_tech_stack_empty_list(repository):
    """Testa que tech_stack vazio lança ValueError."""
    plan = ArchitecturePlan(
        plan_id="test-3",
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[Component(name="api", stack="python")],
        patterns=[Pattern.API_GATEWAY],
        rationale="Test",
        tech_stack=[],  # Lista vazia
    )

    with pytest.raises(ValueError, match="tech_stack cannot be empty"):
        repository._validate_extended_fields(plan)


def test_validate_diagrams_empty_list(repository):
    """Testa que diagrams vazio lança ValueError."""
    plan = ArchitecturePlan(
        plan_id="test-4",
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[Component(name="api", stack="python")],
        patterns=[Pattern.API_GATEWAY],
        rationale="Test",
        diagrams=[],  # Lista vazia
    )

    with pytest.raises(ValueError, match="diagrams cannot be empty"):
        repository._validate_extended_fields(plan)


def test_validate_valid_extended_fields(repository):
    """Testa que campos estendidos válidos não lançam exceção."""
    ctx = BoundedContext(
        name="Identity",
        description="Gestão de identidade",
        responsibilities=["Auth"],
        domain_models=["User"],
    )

    choice = TechChoice(category="language", name="Python", version="3.12", rationale="Type hints")

    diagram = Diagram(
        diagram_id="diag-1",
        type=DiagramType.C4_CONTEXT,
        title="Context",
        mermaid_code="graph TD\nA[User]",
    )

    plan = ArchitecturePlan(
        plan_id="test-5",
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[Component(name="api", stack="python")],
        patterns=[Pattern.API_GATEWAY],
        rationale="Test",
        bounded_contexts=[ctx],
        tech_stack=[choice],
        diagrams=[diagram],
    )

    # Não deve lançar exceção
    repository._validate_extended_fields(plan)


def test_validate_none_extended_fields(repository):
    """Testa que campos None são válidos (campos opcionais)."""
    plan = ArchitecturePlan(
        plan_id="test-6",
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[Component(name="api", stack="python")],
        patterns=[Pattern.API_GATEWAY],
        rationale="Test",
        bounded_contexts=None,
        tech_stack=None,
        diagrams=None,
    )

    # Não deve lançar exceção
    repository._validate_extended_fields(plan)
