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


class TestResourceAllocatorLoadPredictorIntegration:
    """Testes de integração com LoadPredictor."""

    @pytest.fixture
    def mock_load_predictor(self):
        """LoadPredictor mock."""
        predictor = AsyncMock()
        predictor.predict_worker_load = AsyncMock(return_value=0.3)
        predictor.predict_queue_time = AsyncMock(return_value=500.0)
        return predictor

    @pytest.mark.asyncio
    async def test_enrich_workers_with_load_predictions_success(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers, mock_load_predictor
    ):
        """Testa enriquecimento bem-sucedido de workers com predições de carga."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics,
            load_predictor=mock_load_predictor
        )

        enriched = await allocator.enrich_workers_with_load_predictions(sample_workers)

        # Verificar que todos os workers foram enriquecidos
        assert len(enriched) == len(sample_workers)

        for worker in enriched:
            assert worker.get("ml_enriched") is True
            assert "predicted_load_pct" in worker
            assert "predicted_queue_ms" in worker
            assert worker.get("predicted_load_pct") == 0.3
            assert worker.get("predicted_queue_ms") == 500.0

    @pytest.mark.asyncio
    async def test_enrich_workers_without_load_predictor(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa que workers são retornados inalterados sem LoadPredictor."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics,
            load_predictor=None
        )

        enriched = await allocator.enrich_workers_with_load_predictions(sample_workers)

        # Workers devem ser inalterados
        assert len(enriched) == len(sample_workers)
        assert enriched[0].get("ml_enriched") is None

    @pytest.mark.asyncio
    async def test_enrich_workers_with_prediction_error(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa tratamento de erros durante enriquecimento."""
        # Criar LoadPredictor que falha para alguns workers
        async def failing_predict(worker_id):
            if worker_id == "worker-002":
                raise Exception("Prediction failed")
            return 0.3

        async def failing_queue(worker_id, ticket=None):
            if worker_id == "worker-002":
                raise Exception("Queue prediction failed")
            return 500.0

        mock_predictor = AsyncMock()
        mock_predictor.predict_worker_load = AsyncMock(side_effect=failing_predict)
        mock_predictor.predict_queue_time = AsyncMock(side_effect=failing_queue)

        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics,
            load_predictor=mock_predictor
        )

        enriched = await allocator.enrich_workers_with_load_predictions(sample_workers)

        # Todos os workers devem ser retornados, mesmo com erros
        assert len(enriched) == len(sample_workers)

        # worker-002 deve estar marcado como não enriquecido
        worker_002 = next(w for w in enriched if w.get("agent_id") == "worker-002")
        assert worker_002.get("ml_enriched") is False

        # Outros workers devem estar enriquecidos
        for worker in enriched:
            if worker.get("agent_id") != "worker-002":
                assert worker.get("ml_enriched") is True

    @pytest.mark.asyncio
    async def test_select_best_worker_with_load_predictions(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers, mock_load_predictor
    ):
        """Testa seleção com enriquecimento de carga."""
        # Configurar predições diferentes para cada worker
        async def predict_load(worker_id):
            if worker_id == "worker-001":
                return 0.2  # Baixa carga - deve ser preferido
            elif worker_id == "worker-002":
                return 0.8  # Alta carga
            return 0.5

        async def predict_queue(worker_id, ticket=None):
            if worker_id == "worker-001":
                return 200.0  # Fila curta
            elif worker_id == "worker-002":
                return 5000.0  # Fila longa
            return 1000.0

        mock_load_predictor.predict_worker_load = AsyncMock(side_effect=predict_load)
        mock_load_predictor.predict_queue_time = AsyncMock(side_effect=predict_queue)

        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics,
            load_predictor=mock_load_predictor
        )

        result = await allocator.select_best_worker(sample_workers, 0.7)

        # worker-001 deve ser selecionado (menor carga e fila)
        assert result is not None
        assert result["agent_id"] == "worker-001"
        assert result.get("ml_enriched") is True
        assert result.get("predicted_load_pct") == 0.2
        assert result.get("predicted_queue_ms") == 200.0

    def test_calculate_agent_score_with_load_predictions(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa cálculo de score com predições de carga."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics,
        )

        # Worker com predições de carga favoráveis
        worker_with_predictions = {
            **sample_workers[0],
            "ml_enriched": True,
            "predicted_load_pct": 0.1,  # Baixa carga
            "predicted_queue_ms": 500.0,  # Fila curta
        }

        score = allocator._calculate_agent_score(worker_with_predictions)

        # Score deve ser alto devido a baixa carga
        assert score > 0.7

    def test_calculate_agent_score_with_high_load_predictions(
        self, mock_registry_client, mock_config, mock_metrics, sample_workers
    ):
        """Testa que score é penalizado com predições de carga desfavoráveis."""
        allocator = ResourceAllocator(
            registry_client=mock_registry_client,
            config=mock_config,
            metrics=mock_metrics,
        )

        # Worker com predições de carga desfavoráveis
        worker_with_high_load = {
            **sample_workers[0],
            "ml_enriched": True,
            "predicted_load_pct": 0.9,  # Alta carga
            "predicted_queue_ms": 9000.0,  # Fila longa
        }

        score_high_load = allocator._calculate_agent_score(worker_with_high_load)

        # Worker sem predições (baseline)
        worker_without_predictions = {**sample_workers[0], "ml_enriched": False}
        score_baseline = allocator._calculate_agent_score(worker_without_predictions)

        # Score com alta carga deve ser menor que baseline
        assert score_high_load < score_baseline
