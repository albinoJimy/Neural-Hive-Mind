"""Tests para FluxoGMonitorService."""

import sys
from pathlib import Path

# Add src to path when running tests
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from unittest.mock import AsyncMock, patch

import pytest

from services.monitor_service import FluxoGMonitorService


@pytest.mark.asyncio()
class TestFluxoGMonitorService:
    """Testes para FluxoGMonitorService."""

    async def test_get_metrics(self):
        """Testa obtenção de métricas."""
        service = FluxoGMonitorService()

        metrics = await service.get_metrics()

        assert metrics.total_workflows >= 0
        assert metrics.running_workflows >= 0
        assert metrics.completed_workflows >= 0
        assert 0.0 <= metrics.success_rate <= 1.0
        assert isinstance(metrics.services_health, dict)

    async def test_get_recent_workflows(self):
        """Testa listagem de workflows recentes."""
        service = FluxoGMonitorService()

        workflows = await service.get_recent_workflows(limit=10)

        assert len(workflows) <= 10
        for wf in workflows:
            assert "workflow_id" in wf
            assert "status" in wf

    async def test_get_workflow_detail(self):
        """Testa detalhes de workflow."""
        service = FluxoGMonitorService()

        detail = await service.get_workflow_detail("test-workflow-id")

        assert detail is not None
        assert detail.workflow_id == "test-workflow-id"
        assert detail.plan_id is not None
        assert len(detail.stages) == 5  # G1-G5

    async def test_check_services_health(self):
        """Testa verificação de saúde dos serviços."""
        service = FluxoGMonitorService()

        with patch.object(service, "_get_http_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            health = await service._check_services_health()

            assert isinstance(health, dict)
            # Verificar que todos os serviços foram checados
            expected_services = [
                "orchestrator",
                "requirements",
                "documentation",
                "knowledge_graph",
                "approval",
            ]
            for service_name in expected_services:
                assert service_name in health

    async def test_get_pending_approvals_empty(self):
        """Testa busca de aprovações pendentes (vazia)."""
        service = FluxoGMonitorService()

        with patch.object(service, "_get_http_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"items": []}
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            approvals = await service.get_pending_approvals()

            assert len(approvals) == 0

    async def test_close(self):
        """Testa fechamento do serviço."""
        service = FluxoGMonitorService()

        # Criar cliente HTTP
        await service._get_http_client()
        assert service._http_client is not None

        # Fechar
        await service.close()
        assert service._http_client is None
