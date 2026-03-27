"""Testes unitários para API REST."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from fastapi.testclient import TestClient
from src.api.app import create_app
from src.api.schemas import ArchitectureRequest, ValidationRequest
from src.models.architecture import Component, ArchitectureType, Pattern


@pytest.fixture
def client():
    """Cliente de teste FastAPI."""
    return TestClient(create_app())


# Health check tests (no mocking needed)
def test_liveness(client):
    """Testa health check liveness."""
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness(client):
    """Testa health check readiness."""
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_create_architecture_invalid(client):
    """Testa validação de intent vazio."""
    response = client.post(
        "/api/v1/architecture",
        json={"intent": ""},
    )

    assert response.status_code == 422  # Validation error


def test_list_architectures():
    """Testa listagem de arquiteturas."""
    # Patch the module-level functions that return singletons
    with patch("src.api.routers.architecture.get_repository") as mock_get_repo:
        mock_repo = Mock()
        mock_repo.list_all = AsyncMock(return_value=[])
        mock_get_repo.return_value = mock_repo

        client = TestClient(create_app())
        response = client.get("/api/v1/architecture")

        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_create_architecture():
    """Testa criação de arquitetura."""
    # Create proper mock response with actual Component objects
    plan_mock = Mock()
    plan_mock.plan_id = "arch-123"
    plan_mock.cognitive_plan_id = "cog-123"
    plan_mock.architecture_type = Mock(value="microservices")
    plan_mock.components = [
        Component(name="api", stack="python/fastapi", replicas=1, ha=False)
    ]
    plan_mock.patterns = [Pattern.REPOSITORY]
    plan_mock.rationale = "Test architecture"
    plan_mock.created_at = datetime.utcnow()

    mock_planner = Mock()
    mock_planner.plan = AsyncMock(return_value=plan_mock)

    mock_repo = Mock()
    mock_repo.create = AsyncMock()

    # Patch the module-level functions that return singletons
    with patch("src.api.routers.architecture.get_planner", return_value=mock_planner):
        with patch("src.api.routers.architecture.get_repository", return_value=mock_repo):
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/architecture",
                json={
                    "intent": "Create API for user management",
                    "context": {"team_size": 5},
                    "cognitive_plan_id": "cog-123",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["plan_id"] == "arch-123"
            assert data["architecture_type"] == "microservices"


def test_get_architecture_not_found():
    """Testa busca de arquitetura inexistente."""
    with patch("src.api.routers.architecture.get_repository") as mock_get_repo:
        mock_repo = Mock()
        mock_repo.get_by_plan_id = AsyncMock(return_value=None)
        mock_get_repo.return_value = mock_repo

        client = TestClient(create_app())
        response = client.get("/api/v1/architecture/nonexistent")

        assert response.status_code == 404


# Validation endpoints tests
def test_validate_repository():
    """Testa validação de repositório."""
    from src.models.validation import Trend

    # Setup engine mock
    report_mock = Mock()
    report_mock.report_id = "val-123"
    report_mock.repo_url = "github.com/test/repo"
    report_mock.branch = "main"
    report_mock.health_score = 75
    report_mock.trend = Trend.STABLE
    report_mock.violations = []
    report_mock.suggestions = []
    report_mock.created_at = datetime.utcnow()

    mock_engine = Mock()
    mock_engine.validate = AsyncMock(return_value=report_mock)

    mock_repo = Mock()
    mock_repo.create = AsyncMock()

    # Patch the module-level functions that return singletons
    with patch("src.api.routers.validation.get_validate_engine", return_value=mock_engine):
        with patch("src.api.routers.validation.get_validation_repository", return_value=mock_repo):
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/validation",
                json={"repo_url": "github.com/test/repo", "branch": "main"},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["report_id"] == "val-123"


def test_get_validation_report_not_found():
    """Testa busca de relatório inexistente."""
    with patch("src.api.routers.validation.get_validation_repository") as mock_get_repo:
        mock_repo = Mock()
        mock_repo.get_by_report_id = AsyncMock(return_value=None)
        mock_get_repo.return_value = mock_repo

        client = TestClient(create_app())
        response = client.get("/api/v1/validation/nonexistent")

        assert response.status_code == 404


def test_list_validations_by_repo():
    """Testa listagem de validações por repositório."""
    with patch("src.api.routers.validation.get_validation_repository") as mock_get_repo:
        mock_repo = Mock()
        mock_repo.get_by_repo_url = AsyncMock(return_value=[])
        mock_get_repo.return_value = mock_repo

        client = TestClient(create_app())
        response = client.get("/api/v1/validation/repo/github.com/test/repo")

        assert response.status_code == 200
        assert isinstance(response.json(), list)
