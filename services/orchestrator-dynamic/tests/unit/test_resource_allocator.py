"""
Testes unitários para ResourceAllocator.

Cobertura:
- Descoberta de workers bem-sucedida
- Tratamento de erros gRPC
- Filtros de descoberta
- Seleção do melhor worker
- Cálculo de scores de agente
- Verificação de disponibilidade
- Tratamento de telemetria
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any
import grpc

from src.scheduler.resource_allocator import ResourceAllocator
from src.clients.service_registry_client import ServiceRegistryClient
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
def mock_registry_client():
    """ServiceRegistryClient mock com discover_agents async."""
    client = AsyncMock(spec=ServiceRegistryClient)
    client.discover_agents = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_config():
    """Config com configurações do Service Registry."""
    config = MagicMock(spec=OrchestratorSettings)
    config.service_registry_endpoint = "service-registry:50051"
    config.service_registry_max_results = 10
    config.service_registry_timeout_seconds = 5
    return config


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock(spec=OrchestratorMetrics)
    metrics.record_discovery_failure = MagicMock()
    return metrics


@pytest.fixture
def sample_workers() -> List[Dict[str, Any]]:
    """Lista de workers com várias características."""
    return [
        {
            "agent_id": "worker-001",
            "agent_type": "worker-agent",
            "status": "HEALTHY",
            "capabilities": ["python", "data-processing"],
            "telemetry": {
                "success_rate": 0.95,
                "avg_duration_ms": 800,
                "total_executions": 100
            },
            "active_tasks": 3,
            "max_concurrent_tasks": 10
        },
        {
            "agent_id": "worker-002",
            "agent_type": "worker-agent",
            "status": "HEALTHY",
            "capabilities": ["python", "ml-inference"],
            "telemetry": {
                "success_rate": 0.90,
                "avg_duration_ms": 1200,
                "total_executions": 50
            },
            "active_tasks": 5,
            "max_concurrent_tasks": 10
        },
        {
            "agent_id": "worker-003",
            "agent_type": "worker-agent",
            "status": "DEGRADED",
            "capabilities": ["python"],
            "telemetry": {
                "success_rate": 0.80,
                "avg_duration_ms": 1500,
                "total_executions": 30
            },
            "active_tasks": 1,
            "max_concurrent_tasks": 10
        }
    ]


@pytest.fixture
def sample_ticket() -> Dict[str, Any]:
    """Ticket padrão para descoberta."""
    return {
        "ticket_id": "ticket-123",
        "required_capabilities": ["python", "data-processing"],
        "namespace": "default",
        "security_level": "standard"
    }


class TestResourceAllocator:
    """Testes para ResourceAllocator."""

    @pytest.mark.asyncio
    async def test_discover_workers_success(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers, sample_ticket
    ):
        """Testa descoberta bem-sucedida de workers."""
        # Configurar mock
        mock_registry_client.discover_agents.return_value = sample_workers

        # Criar allocator
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        # Executar
        result = await allocator.discover_workers(sample_ticket)

        # Verificar
        assert len(result) == 3
        assert result[0]["agent_id"] == "worker-001"

        # Verificar chamada ao registry
        mock_registry_client.discover_agents.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_workers_grpc_error(
        self, mock_registry_client, mock_config, mock_metrics, sample_ticket
    ):
        """Testa tratamento de erro gRPC."""
        # Configurar erro
        mock_registry_client.discover_agents.side_effect = grpc.RpcError("Connection failed")

        # Criar allocator
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        # Executar
        result = await allocator.discover_workers(sample_ticket)

        # Verificar lista vazia retornada
        assert result == []

        # Verificar métrica de falha
        mock_metrics.record_discovery_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_workers_with_filters(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers, sample_ticket
    ):
        """Verifica que filtros corretos são aplicados."""
        mock_registry_client.discover_agents.return_value = sample_workers

        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        await allocator.discover_workers(sample_ticket)

        # Verificar filtros passados
        call_args = mock_registry_client.discover_agents.call_args
        filters = call_args[1] if len(call_args) > 1 else call_args[0][0]

        assert "namespace" in str(filters) or sample_ticket["namespace"] in str(filters)

    def test_select_best_worker_single_worker(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa seleção com um único worker."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        workers = [sample_workers[0]]
        priority_score = 0.7

        result = allocator.select_best_worker(workers, priority_score)

        # Verificar worker selecionado
        assert result is not None
        assert result["agent_id"] == "worker-001"
        assert "composite_score" in result

        # Verificar cálculo: (agent_score * 0.6) + (priority_score * 0.4)
        # Agent score deve ser alto devido a HEALTHY + boa telemetria
        assert result["composite_score"] > 0.7

    def test_select_best_worker_multiple_workers(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa seleção com múltiplos workers."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        priority_score = 0.75

        result = allocator.select_best_worker(sample_workers, priority_score)

        # Verificar que melhor worker foi selecionado
        assert result is not None

        # worker-001 deve ter maior score (HEALTHY + melhor telemetria)
        assert result["agent_id"] == "worker-001"

    def test_select_best_worker_empty_list(
        self, mock_registry_client, mock_config, mock_metrics
    ):
        """Testa seleção com lista vazia."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        result = allocator.select_best_worker([], 0.5)

        assert result is None

    def test_select_best_worker_all_unavailable(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa seleção quando todos os workers estão indisponíveis."""
        # Marcar todos como UNHEALTHY
        for worker in sample_workers:
            worker["status"] = "UNHEALTHY"

        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        result = allocator.select_best_worker(sample_workers, 0.5)

        # Nenhum worker disponível
        assert result is None

    def test_calculate_agent_score_healthy_high_success(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa score de agente HEALTHY com alta taxa de sucesso."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        agent = sample_workers[0]  # HEALTHY, 95% success

        score = allocator._calculate_agent_score(agent)

        # Esperado: score alto (> 0.8)
        assert score >= 0.80
        assert score <= 1.0

    def test_calculate_agent_score_degraded(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa score de agente DEGRADED."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        agent = sample_workers[2]  # DEGRADED

        score = allocator._calculate_agent_score(agent)

        # Esperado: health_score = 0.6
        # Score deve ser menor que HEALTHY
        assert score < 0.80

    def test_calculate_agent_score_no_telemetry(
        self, mock_registry_client, mock_config, mock_metrics
    ):
        """Testa score quando não há dados de telemetria."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        agent = {
            "agent_id": "worker-no-telemetry",
            "status": "HEALTHY",
            "capabilities": ["python"]
        }

        score = allocator._calculate_agent_score(agent)

        # Telemetria neutra (0.5), health HEALTHY (1.0)
        # Score = (1.0 * 0.5) + (0.5 * 0.5) = 0.75
        assert abs(score - 0.75) < 0.1

    def test_calculate_telemetry_score_components(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Verifica fórmula de score de telemetria."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        telemetry = sample_workers[0]["telemetry"]

        score = allocator._calculate_telemetry_score(telemetry)

        # Fórmula: success_rate*0.6 + duration_score*0.2 + experience_score*0.2
        # success_rate = 0.95
        # duration_score depende de avg_duration_ms (quanto menor, melhor)
        # experience_score depende de total_executions

        assert 0.0 <= score <= 1.0
        # Com 95% success, score deve ser alto
        assert score > 0.7

    def test_is_worker_available_healthy(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa worker HEALTHY disponível."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        agent = sample_workers[0]

        result = allocator._is_worker_available(agent)

        assert result is True

    def test_is_worker_available_unhealthy(
        self, mock_registry_client, mock_config, mock_metrics
    ):
        """Testa worker UNHEALTHY indisponível."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        agent = {
            "agent_id": "worker-unhealthy",
            "status": "UNHEALTHY",
            "capabilities": ["python"]
        }

        result = allocator._is_worker_available(agent)

        assert result is False

    def test_is_worker_available_capacity_full(
        self, mock_registry_client, mock_config, mock_metrics
    ):
        """Testa worker com capacidade cheia."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        agent = {
            "agent_id": "worker-full",
            "status": "HEALTHY",
            "capabilities": ["python"],
            "active_tasks": 10,
            "max_concurrent_tasks": 10
        }

        result = allocator._is_worker_available(agent)

        assert result is False

    def test_is_worker_available_capacity_available(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa worker com capacidade disponível."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics
        )

        agent = sample_workers[0]  # 3/10 tasks

        result = allocator._is_worker_available(agent)

        assert result is True
