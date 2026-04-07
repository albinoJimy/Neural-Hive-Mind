"""
Testes de API REST para Load Balancer

Testa endpoints de gerenciamento de workers e atribuição de tarefas.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.services.load_balancer import BalancingStrategy, TaskAssignment


@pytest.fixture
def mock_app_state():
    """Mock app state"""
    state = MagicMock()
    state.load_balancer = MagicMock()
    state.load_balancer.is_running = True
    state.load_balancer.register_worker = AsyncMock(return_value=True)
    state.load_balancer.unregister_worker = AsyncMock(return_value=True)
    state.load_balancer.update_worker_metrics = AsyncMock(return_value=True)
    state.load_balancer.get_workers_status = AsyncMock(
        return_value={
            "worker-1": {
                "active_tasks": 3,
                "completed_tasks": 100,
                "failed_tasks": 2,
                "capacity": 1.0,
                "is_healthy": True,
            }
        }
    )
    state.load_balancer.get_statistics = AsyncMock(
        return_value={
            "total_workers": 1,
            "healthy_workers": 1,
            "unhealthy_workers": 0,
            "total_active_tasks": 3,
            "total_completed_tasks": 100,
            "total_failed_tasks": 2,
            "strategy": "round_robin",
        }
    )
    state.load_balancer.assign_task = AsyncMock(
        return_value=TaskAssignment(
            worker_id="worker-1",
            strategy=BalancingStrategy.ROUND_ROBIN,
            assigned_at=datetime.now(timezone.utc),
        )
    )
    state.load_balancer.complete_task = AsyncMock(return_value=True)
    return state


@pytest.fixture
def app(mock_app_state):
    """Fixture FastAPI app"""
    from fastapi import FastAPI
    from src.api.workers import router

    app = FastAPI()
    app.state.app_state = mock_app_state
    app.include_router(router)
    return app


class TestRegisterWorkerEndpoint:
    """Testes do endpoint POST /api/v1/workers/register"""

    @pytest.mark.asyncio
    async def test_register_worker_success(self, async_client: AsyncClient):
        """Testa registro bem-sucedido de worker"""
        payload = {
            "worker_id": "worker-1",
            "capacity": 1.5,
            "metadata": {"location": "zone-1"},
        }

        response = await async_client.post("/api/v1/workers/register", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["worker_id"] == "worker-1"
        assert data["message"] == "Worker registered successfully"

    @pytest.mark.asyncio
    async def test_register_worker_default_capacity(self, async_client: AsyncClient):
        """Testa registro com capacidade padrão"""
        payload = {"worker_id": "worker-2"}

        response = await async_client.post("/api/v1/workers/register", json=payload)

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_register_worker_invalid_capacity(self, async_client: AsyncClient):
        """Testa registro com capacidade inválida"""
        payload = {"worker_id": "worker-1", "capacity": 0.0}  # Deve ser >= 0.1

        response = await async_client.post("/api/v1/workers/register", json=payload)

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_worker_disabled(self, app, async_client: AsyncClient):
        """Testa resposta quando load balancer está desabilitado"""
        app.state.app_state.load_balancer = None

        payload = {"worker_id": "worker-1"}

        response = await async_client.post("/api/v1/workers/register", json=payload)

        assert response.status_code == 503


class TestUnregisterWorkerEndpoint:
    """Testes do endpoint DELETE /api/v1/workers/{worker_id}"""

    @pytest.mark.asyncio
    async def test_unregister_worker_success(self, async_client: AsyncClient):
        """Testa remoção bem-sucedida de worker"""
        response = await async_client.delete("/api/v1/workers/worker-1")

        assert response.status_code == 200
        data = response.json()
        assert data["worker_id"] == "worker-1"
        assert data["message"] == "Worker unregistered successfully"


class TestUpdateWorkerMetricsEndpoint:
    """Testes do endpoint POST /api/v1/workers/{worker_id}/metrics"""

    @pytest.mark.asyncio
    async def test_update_metrics_success(self, async_client: AsyncClient):
        """Testa atualização bem-sucedida de métricas"""
        payload = {
            "active_tasks": 5,
            "completed_tasks": 100,
            "failed_tasks": 2,
            "avg_processing_time_ms": 150.5,
        }

        response = await async_client.post("/api/v1/workers/worker-1/metrics", json=payload)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_metrics_partial(self, async_client: AsyncClient):
        """Testa atualização parcial de métricas"""
        payload = {"active_tasks": 10}

        response = await async_client.post("/api/v1/workers/worker-1/metrics", json=payload)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_metrics_invalid_value(self, async_client: AsyncClient):
        """Testa atualização com valor inválido"""
        payload = {"active_tasks": -1}  # Deve ser >= 0

        response = await async_client.post("/api/v1/workers/worker-1/metrics", json=payload)

        assert response.status_code == 422


class TestGetWorkersStatusEndpoint:
    """Testes do endpoint GET /api/v1/workers"""

    @pytest.mark.asyncio
    async def test_get_workers_status(self, async_client: AsyncClient):
        """Testa obtenção de status de todos workers"""
        response = await async_client.get("/api/v1/workers")

        assert response.status_code == 200
        data = response.json()
        assert "workers" in data
        assert "count" in data
        assert data["count"] >= 0


class TestGetStatisticsEndpoint:
    """Testes do endpoint GET /api/v1/workers/statistics"""

    @pytest.mark.asyncio
    async def test_get_statistics(self, async_client: AsyncClient):
        """Testa obtenção de estatísticas"""
        response = await async_client.get("/api/v1/workers/statistics")

        assert response.status_code == 200
        data = response.json()
        assert "total_workers" in data
        assert "healthy_workers" in data
        assert "unhealthy_workers" in data
        assert "total_active_tasks" in data
        assert "strategy" in data


class TestAssignTaskEndpoint:
    """Testes do endpoint POST /api/v1/workers/assign"""

    @pytest.mark.asyncio
    async def test_assign_task_success(self, async_client: AsyncClient):
        """Testa atribuição bem-sucedida de tarefa"""
        payload = {"task_id": "task-123", "task_data": {"type": "query"}}

        response = await async_client.post("/api/v1/workers/assign", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-123"
        assert "worker_id" in data
        assert "strategy" in data

    @pytest.mark.asyncio
    async def test_assign_task_no_workers(self, app, async_client: AsyncClient):
        """Testa atribuição quando não há workers disponíveis"""
        app.state.app_state.load_balancer.assign_task = AsyncMock(return_value=None)

        payload = {"task_id": "task-123"}

        response = await async_client.post("/api/v1/workers/assign", json=payload)

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_assign_task_with_strategy(self, async_client: AsyncClient):
        """Testa atribuição com estratégia específica"""
        payload = {
            "task_id": "task-123",
            "strategy": "least_loaded",
        }

        response = await async_client.post("/api/v1/workers/assign", json=payload)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_assign_task_invalid_strategy(self, async_client: AsyncClient):
        """Testa atribuição com estratégia inválida"""
        payload = {"task_id": "task-123", "strategy": "invalid_strategy"}

        response = await async_client.post("/api/v1/workers/assign", json=payload)

        assert response.status_code == 400


class TestCompleteTaskEndpoint:
    """Testes do endpoint POST /api/v1/workers/complete"""

    @pytest.mark.asyncio
    async def test_complete_task_success(self, async_client: AsyncClient):
        """Testa conclusão bem-sucedida de tarefa"""
        payload = {
            "worker_id": "worker-1",
            "task_id": "task-123",
            "success": True,
            "processing_time_ms": 200.0,
        }

        response = await async_client.post("/api/v1/workers/complete", json=payload)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_complete_task_failure(self, async_client: AsyncClient):
        """Testa conclusão com falha"""
        payload = {
            "worker_id": "worker-1",
            "task_id": "task-123",
            "success": False,
        }

        response = await async_client.post("/api/v1/workers/complete", json=payload)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_complete_task_invalid_value(self, async_client: AsyncClient):
        """Testa conclusão com valor inválido"""
        payload = {
            "worker_id": "worker-1",
            "task_id": "task-123",
            "processing_time_ms": -1.0,  # Deve ser >= 0
        }

        response = await async_client.post("/api/v1/workers/complete", json=payload)

        assert response.status_code == 422
