"""Tests para o router de testes."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from main import app
from models.tests import TestType, TestFramework


class TestTestsRouter:
    """Testes para o router de testes."""

    @pytest.fixture
    async def client(self):
        """Cliente HTTP de teste."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @pytest.fixture
    def mock_generator(self):
        """Mock do gerador de testes."""
        with patch("api.routers.tests.TestGeneratorService") as mock:
            service = AsyncMock()
            mock.return_value = service
            yield service

    async def test_generate_tests_endpoint(self, client, mock_generator):
        """Testa endpoint de geração de testes."""
        mock_generator.generate_tests.return_value = mock_generator

        response = await client.post(
            "/api/v1/tests/generate",
            json={
                "requirements": [
                    {
                        "id": "REQ-001",
                        "title": "Test Requirement",
                        "description": "Test description",
                    }
                ],
                "framework": "pytest",
                "language": "python",
            },
        )

        assert response.status_code in [200, 201]
        mock_generator.generate_tests.assert_called_once()

    async def test_generate_from_requirements(self, client, mock_generator):
        """Testa endpoint de geração a partir de requisitos."""
        mock_generator.generate_tests.return_value = mock_generator

        response = await client.post(
            "/api/v1/tests/generate/from-requirements",
            json={
                "requirements": [
                    {
                        "id": "REQ-001",
                        "title": "Login",
                        "description": "User login functionality",
                        "acceptance_criteria": ["Valid login works"],
                    }
                ],
                "test_type": "unit",
                "framework": "pytest",
            },
        )

        assert response.status_code in [200, 201]

    async def test_generate_from_user_stories(self, client, mock_generator):
        """Testa endpoint de geração a partir de user stories."""
        mock_generator.generate_tests.return_value = mock_generator

        response = await client.post(
            "/api/v1/tests/generate/from-user-stories",
            json={
                "user_stories": [
                    {
                        "id": "US-001",
                        "title": "Login Story",
                        "description": "As a user, I want to login",
                        "acceptance_criteria": [
                            {
                                "id": "AC-001",
                                "given": "on login page",
                                "when": "enter valid credentials",
                                "then": "redirected to dashboard",
                            }
                        ],
                    }
                ],
                "test_type": "e2e",
                "framework": "robot",
            },
        )

        assert response.status_code in [200, 201]

    async def test_coverage_metrics(self, client):
        """Testa endpoint de métricas de cobertura."""
        response = await client.get("/api/v1/tests/coverage")

        assert response.status_code == 200
        data = response.json()
        assert "coverage_percentage" in data

    async def test_list_suites(self, client):
        """Testa listagem de suítes de testes."""
        response = await client.get("/api/v1/tests/suites")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_health_check(self, client):
        """Testa health check."""
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    async def test_root_endpoint(self, client):
        """Testa endpoint raiz."""
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data


class TestTestsRouterValidation:
    """Testes de validação do router."""

    @pytest.fixture
    async def client(self):
        """Cliente HTTP de teste."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    async def test_invalid_test_type(self, client):
        """Testa validação de tipo de teste inválido."""
        response = await client.post(
            "/api/v1/tests/generate",
            json={
                "requirements": [{"id": "REQ-001", "title": "Test"}],
                "test_type": "invalid_type",
                "framework": "pytest",
            },
        )

        assert response.status_code == 422

    async def test_invalid_framework(self, client):
        """Testa validação de framework inválido."""
        response = await client.post(
            "/api/v1/tests/generate",
            json={
                "requirements": [{"id": "REQ-001", "title": "Test"}],
                "framework": "invalid_framework",
            },
        )

        assert response.status_code == 422

    async def test_missing_requirements(self, client):
        """Testa validação de requisitos ausentes."""
        response = await client.post(
            "/api/v1/tests/generate",
            json={"framework": "pytest", "language": "python"},
        )

        assert response.status_code == 422
