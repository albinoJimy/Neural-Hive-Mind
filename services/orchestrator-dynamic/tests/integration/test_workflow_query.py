"""
Testes de integração para o endpoint de query de workflow Temporal.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.fixture
def mock_app_state():
    """Mock do app_state para testes."""
    with patch('src.main.app_state') as mock_state:
        yield mock_state


@pytest.fixture
def client():
    """Cliente de teste FastAPI."""
    from src.main import app
    return TestClient(app)


class TestWorkflowQueryEndpoint:
    """Testes do endpoint /api/v1/workflows/{workflow_id}/query."""

    @pytest.mark.asyncio
    async def test_workflow_query_get_tickets_success(self, mock_app_state):
        """Testa query get_tickets com sucesso."""
        from src.main import app

        # Mock Temporal client
        mock_handle = AsyncMock()
        mock_handle.query = AsyncMock(return_value=[
            {
                "ticket_id": "ticket-001",
                "plan_id": "plan-456",
                "task_id": "task-1",
                "task_type": "BUILD",
                "status": "PENDING",
            },
            {
                "ticket_id": "ticket-002",
                "plan_id": "plan-456",
                "task_id": "task-2",
                "task_type": "DEPLOY",
                "status": "PENDING",
            },
        ])

        mock_temporal = MagicMock()
        mock_temporal.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_app_state.temporal_client = mock_temporal
        mock_app_state.redis_client = None

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/workflow-123/query",
                json={"query_name": "get_tickets"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "workflow-123"
        assert data["query_name"] == "get_tickets"
        assert "tickets" in data["result"]
        assert len(data["result"]["tickets"]) == 2

    @pytest.mark.asyncio
    async def test_workflow_query_get_status_success(self, mock_app_state):
        """Testa query get_status com sucesso."""
        from src.main import app

        mock_handle = AsyncMock()
        mock_handle.query = AsyncMock(return_value={
            "status": "generating_tickets",
            "tickets_generated": 5,
            "workflow_result": {},
            "sla_warnings": [],
        })

        mock_temporal = MagicMock()
        mock_temporal.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/workflow-123/query",
                json={"query_name": "get_status"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["query_name"] == "get_status"
        assert data["result"]["status"] == "generating_tickets"

    @pytest.mark.asyncio
    async def test_workflow_query_temporal_unavailable(self, mock_app_state):
        """Testa erro quando Temporal não está disponível."""
        from src.main import app

        mock_app_state.temporal_client = None

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/workflow-123/query",
                json={"query_name": "get_tickets"}
            )

        assert response.status_code == 503
        assert "Temporal client not available" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_workflow_query_not_found(self, mock_app_state):
        """Testa erro quando workflow não é encontrado."""
        from src.main import app

        mock_handle = AsyncMock()
        mock_handle.query = AsyncMock(side_effect=Exception("Workflow not found"))

        mock_temporal = MagicMock()
        mock_temporal.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/nonexistent-workflow/query",
                json={"query_name": "get_tickets"}
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_workflow_query_invalid_query_name(self, mock_app_state):
        """Testa query com nome inválido."""
        from src.main import app

        mock_handle = AsyncMock()
        mock_handle.query = AsyncMock(side_effect=Exception("Query invalid_query does not exist"))

        mock_temporal = MagicMock()
        mock_temporal.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/workflow-123/query",
                json={"query_name": "invalid_query"}
            )

        assert response.status_code == 500
        assert "Failed to query workflow" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_workflow_query_cache_hit(self, mock_app_state):
        """Testa cache hit para queries de tickets."""
        from src.main import app

        cached_tickets = [
            {"ticket_id": "cached-ticket-001", "status": "PENDING"}
        ]

        mock_app_state.temporal_client = MagicMock()

        with patch('src.main.get_cached_tickets_by_workflow', new_callable=AsyncMock) as mock_cache:
            mock_cache.return_value = cached_tickets

            async with AsyncClient(app=app, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/workflows/workflow-123/query",
                    json={"query_name": "get_tickets"}
                )

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["cached"] is True
        assert len(data["result"]["tickets"]) == 1
        assert data["result"]["tickets"][0]["ticket_id"] == "cached-ticket-001"


class TestWorkflowQueryValidation:
    """Testes de validação do request de query."""

    @pytest.mark.asyncio
    async def test_workflow_query_missing_query_name(self, mock_app_state):
        """Testa erro quando query_name não é fornecido."""
        from src.main import app

        mock_app_state.temporal_client = MagicMock()

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/workflow-123/query",
                json={}
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_workflow_query_with_args(self, mock_app_state):
        """Testa query com argumentos opcionais."""
        from src.main import app

        mock_handle = AsyncMock()
        mock_handle.query = AsyncMock(return_value={"custom": "result"})

        mock_temporal = MagicMock()
        mock_temporal.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/workflow-123/query",
                json={
                    "query_name": "custom_query",
                    "args": ["arg1", "arg2"]
                }
            )

        assert response.status_code == 200
        mock_handle.query.assert_called_once_with("custom_query", "arg1", "arg2")
