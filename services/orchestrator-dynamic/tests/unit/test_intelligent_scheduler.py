"""
Testes unitários para IntelligentScheduler.

Cobertura:
- Alocação bem-sucedida com workers descobertos
- Fallback quando nenhum worker está disponível
- Fallback quando nenhum worker adequado é encontrado
- Boost de prioridade com predições ML
- Cache hit/miss
- Expiração de cache
- Timeout de descoberta
- Exceções na descoberta
- Medição de latência
- Cálculo de score composto
- Geração de chave de cache
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any

from src.scheduler.intelligent_scheduler import IntelligentScheduler
from src.scheduler.priority_calculator import PriorityCalculator
from src.scheduler.resource_allocator import ResourceAllocator
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
def mock_config():
    """Config mock com configurações do scheduler."""
    config = MagicMock(spec=OrchestratorSettings)
    config.service_registry_cache_ttl_seconds = 60
    config.service_registry_timeout_seconds = 5
    config.scheduler_priority_weights = {"risk": 0.4, "qos": 0.3, "sla": 0.3}
    return config


@pytest.fixture
def mock_metrics():
    """Metrics mock com todos os métodos de gravação."""
    metrics = MagicMock(spec=OrchestratorMetrics)
    metrics.record_scheduler_allocation = MagicMock()
    metrics.record_priority_score = MagicMock()
    metrics.record_workers_discovered = MagicMock()
    metrics.record_cache_hit = MagicMock()
    metrics.record_discovery_failure = MagicMock()
    return metrics


@pytest.fixture
def mock_priority_calculator():
    """PriorityCalculator mock retornando scores configuráveis."""
    calc = MagicMock(spec=PriorityCalculator)
    calc.calculate_priority_score = MagicMock(return_value=0.75)
    return calc


@pytest.fixture
def mock_resource_allocator():
    """ResourceAllocator mock com métodos async."""
    allocator = AsyncMock(spec=ResourceAllocator)
    allocator.discover_workers = AsyncMock(return_value=[])
    allocator.select_best_worker = MagicMock(return_value=None)
    return allocator


@pytest.fixture
def sample_ticket() -> Dict[str, Any]:
    """Ticket padrão com todos os campos obrigatórios."""
    return {
        "ticket_id": "ticket-123",
        "risk_band": "normal",
        "qos": {
            "delivery_mode": "AT_LEAST_ONCE",
            "consistency": "EVENTUAL",
            "durability": "PERSISTENT"
        },
        "sla": {
            "deadline": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            "timeout_ms": 3600000
        },
        "required_capabilities": ["python", "data-processing"],
        "namespace": "default",
        "security_level": "standard",
        "estimated_duration_ms": 1000,
        "created_at": datetime.utcnow().isoformat()
    }


@pytest.fixture
def sample_workers() -> List[Dict[str, Any]]:
    """Lista de workers com diferentes características."""
    return [
        {
            "agent_id": "worker-001",
            "agent_type": "worker-agent",
            "score": 0.85,
            "capabilities": ["python", "data-processing"],
            "status": "HEALTHY",
            "telemetry": {
                "success_rate": 0.95,
                "avg_duration_ms": 800,
                "total_executions": 100
            }
        },
        {
            "agent_id": "worker-002",
            "agent_type": "worker-agent",
            "score": 0.70,
            "capabilities": ["python", "data-processing"],
            "status": "HEALTHY",
            "telemetry": {
                "success_rate": 0.90,
                "avg_duration_ms": 1200,
                "total_executions": 50
            }
        }
    ]


class TestIntelligentScheduler:
    """Testes para IntelligentScheduler."""

    @pytest.mark.asyncio
    async def test_schedule_ticket_success_with_workers(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket, sample_workers
    ):
        """Testa alocação bem-sucedida com workers descobertos."""
        # Configurar mocks
        mock_resource_allocator.discover_workers.return_value = sample_workers
        mock_resource_allocator.select_best_worker.return_value = sample_workers[0]
        mock_priority_calculator.calculate_priority_score.return_value = 0.75

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Executar
        result = await scheduler.schedule_ticket(sample_ticket)

        # Verificar
        assert "allocation_metadata" in result
        assert result["allocation_metadata"]["agent_id"] == "worker-001"
        assert result["allocation_metadata"]["allocation_method"] == "intelligent_scheduler"
        assert result["allocation_metadata"]["priority_score"] == 0.75
        assert result["allocation_metadata"]["agent_score"] == 0.85
        assert result["allocation_metadata"]["workers_evaluated"] == 2

        # Verificar chamadas
        mock_resource_allocator.discover_workers.assert_called_once()
        mock_priority_calculator.calculate_priority_score.assert_called_once_with(sample_ticket)
        mock_metrics.record_scheduler_allocation.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_ticket_no_workers_fallback(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket
    ):
        """Testa fallback quando lista de workers está vazia."""
        # Configurar mocks
        mock_resource_allocator.discover_workers.return_value = []

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Executar
        result = await scheduler.schedule_ticket(sample_ticket)

        # Verificar fallback
        assert result["allocation_metadata"]["allocation_method"] == "fallback_stub"
        assert result["allocation_metadata"]["agent_id"] == "worker-agent-pool"
        assert result["allocation_metadata"]["workers_evaluated"] == 0

    @pytest.mark.asyncio
    async def test_schedule_ticket_no_suitable_worker_fallback(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket, sample_workers
    ):
        """Testa fallback quando select_best_worker retorna None."""
        # Configurar mocks
        mock_resource_allocator.discover_workers.return_value = sample_workers
        mock_resource_allocator.select_best_worker.return_value = None

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Executar
        result = await scheduler.schedule_ticket(sample_ticket)

        # Verificar fallback
        assert result["allocation_metadata"]["allocation_method"] == "fallback_stub"
        assert result["allocation_metadata"]["agent_id"] == "worker-agent-pool"

    @pytest.mark.asyncio
    async def test_schedule_ticket_with_ml_predictions_priority_boost(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket, sample_workers
    ):
        """Testa boost de prioridade com predições ML."""
        # Adicionar predições ao ticket
        sample_ticket["predictions"] = {
            "duration_ms": 1600,  # 160% do estimado
            "anomaly": {
                "is_anomaly": False,
                "anomaly_score": 0.12,
                "anomaly_type": None
            }
        }

        # Configurar mocks
        mock_resource_allocator.discover_workers.return_value = sample_workers
        mock_resource_allocator.select_best_worker.return_value = sample_workers[0]
        mock_priority_calculator.calculate_priority_score.return_value = 0.75

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Executar
        result = await scheduler.schedule_ticket(sample_ticket)

        # Verificar boost (0.75 * 1.2 = 0.9)
        assert result["allocation_metadata"]["priority_score"] == min(0.75 * 1.2, 1.0)

    @pytest.mark.asyncio
    async def test_schedule_ticket_cache_hit(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket, sample_workers
    ):
        """Testa cache hit - discover_workers chamado apenas uma vez."""
        # Configurar mocks
        mock_resource_allocator.discover_workers.return_value = sample_workers
        mock_resource_allocator.select_best_worker.return_value = sample_workers[0]

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Executar duas vezes
        await scheduler.schedule_ticket(sample_ticket)
        await scheduler.schedule_ticket(sample_ticket)

        # Verificar: discover_workers chamado apenas uma vez
        assert mock_resource_allocator.discover_workers.call_count == 1

        # Verificar cache hit gravado
        mock_metrics.record_cache_hit.assert_called()

    @pytest.mark.asyncio
    async def test_schedule_ticket_cache_miss_different_capabilities(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket, sample_workers
    ):
        """Testa cache miss com capabilities diferentes."""
        # Configurar mocks
        mock_resource_allocator.discover_workers.return_value = sample_workers
        mock_resource_allocator.select_best_worker.return_value = sample_workers[0]

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Primeira chamada
        await scheduler.schedule_ticket(sample_ticket)

        # Segunda chamada com capabilities diferentes
        sample_ticket["required_capabilities"] = ["python", "ml-inference"]
        await scheduler.schedule_ticket(sample_ticket)

        # Verificar: discover_workers chamado duas vezes
        assert mock_resource_allocator.discover_workers.call_count == 2

    @pytest.mark.asyncio
    async def test_schedule_ticket_cache_expiration(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket, sample_workers
    ):
        """Testa expiração do cache."""
        # Configurar TTL curto
        mock_config.service_registry_cache_ttl_seconds = 1

        # Configurar mocks
        mock_resource_allocator.discover_workers.return_value = sample_workers
        mock_resource_allocator.select_best_worker.return_value = sample_workers[0]

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Primeira chamada
        await scheduler.schedule_ticket(sample_ticket)

        # Aguardar expiração
        await asyncio.sleep(1.1)

        # Segunda chamada
        await scheduler.schedule_ticket(sample_ticket)

        # Verificar: discover_workers chamado duas vezes
        assert mock_resource_allocator.discover_workers.call_count == 2

    @pytest.mark.asyncio
    async def test_schedule_ticket_discovery_timeout(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket
    ):
        """Testa timeout na descoberta de workers."""
        # Configurar timeout
        async def slow_discovery(*args, **kwargs):
            await asyncio.sleep(6)  # Excede timeout de 5s
            return []

        mock_resource_allocator.discover_workers.side_effect = slow_discovery

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Executar
        result = await scheduler.schedule_ticket(sample_ticket)

        # Verificar fallback
        assert result["allocation_metadata"]["allocation_method"] == "fallback_stub"

        # Verificar métrica de falha
        mock_metrics.record_discovery_failure.assert_called()

    @pytest.mark.asyncio
    async def test_schedule_ticket_discovery_exception(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket
    ):
        """Testa exceção na descoberta de workers."""
        # Configurar exceção
        mock_resource_allocator.discover_workers.side_effect = Exception("Service Registry error")

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Executar
        result = await scheduler.schedule_ticket(sample_ticket)

        # Verificar fallback gracioso
        assert result["allocation_metadata"]["allocation_method"] == "fallback_stub"

    @pytest.mark.asyncio
    async def test_schedule_ticket_latency_measurement(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket, sample_workers
    ):
        """Testa medição de latência."""
        # Configurar mocks
        mock_resource_allocator.discover_workers.return_value = sample_workers
        mock_resource_allocator.select_best_worker.return_value = sample_workers[0]

        # Criar scheduler
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Executar
        await scheduler.schedule_ticket(sample_ticket)

        # Verificar que métrica foi gravada com duração > 0
        mock_metrics.record_scheduler_allocation.assert_called_once()
        call_args = mock_metrics.record_scheduler_allocation.call_args
        assert call_args[1]["duration_seconds"] > 0

    def test_calculate_composite_score(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator
    ):
        """Testa cálculo de score composto."""
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Testar cálculo: (agent_score * 0.6) + (priority_score * 0.4)
        agent_score = 0.8
        priority_score = 0.7
        expected = (0.8 * 0.6) + (0.7 * 0.4)  # 0.76

        result = scheduler._calculate_composite_score(priority_score, agent_score)

        assert abs(result - expected) < 0.01

        # Testar limites
        assert scheduler._calculate_composite_score(1.0, 1.0) == 1.0
        assert scheduler._calculate_composite_score(0.0, 0.0) == 0.0

    def test_build_cache_key(
        self, mock_config, mock_metrics, mock_priority_calculator,
        mock_resource_allocator, sample_ticket
    ):
        """Testa geração de chave de cache."""
        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=mock_priority_calculator,
            resource_allocator=mock_resource_allocator
        )

        # Gerar chave
        key = scheduler._build_cache_key(sample_ticket)

        # Verificar formato: namespace:security_level:capability1:capability2 (sorted)
        expected_capabilities = ":".join(sorted(sample_ticket["required_capabilities"]))
        expected = f"{sample_ticket['namespace']}:{sample_ticket['security_level']}:{expected_capabilities}"

        assert key == expected

        # Testar que capabilities são ordenadas
        sample_ticket["required_capabilities"] = ["z-capability", "a-capability"]
        key = scheduler._build_cache_key(sample_ticket)
        assert "a-capability" in key
        assert key.index("a-capability") < key.index("z-capability")
