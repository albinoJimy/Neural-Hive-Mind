"""
Testes de integração para ML Scheduling (LoadPredictor + SchedulingOptimizer + ResourceAllocator).
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.ml.load_predictor import LoadPredictor
from src.ml.scheduling_optimizer import SchedulingOptimizer
from src.scheduler.resource_allocator import ResourceAllocator
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
def config():
    """Configuração real para testes de integração."""
    config = Mock(spec=OrchestratorSettings)
    config.enable_optimizer_integration = True
    config.ml_local_load_prediction_enabled = True
    config.ml_allocation_outcomes_enabled = True
    config.ml_allocation_outcomes_topic = 'ml.allocation_outcomes'
    config.ml_optimization_timeout_seconds = 2
    config.ml_local_load_window_minutes = 60
    config.ml_local_load_cache_ttl_seconds = 30
    config.mongodb_collection_tickets = 'execution_tickets'
    config.service_registry_max_results = 5
    return config


@pytest.fixture
def mongodb_client_with_data():
    """MongoDB mockado com dados históricos."""
    mock = AsyncMock()

    # Dados de completions
    completions = [
        {'actual_duration_ms': 2000.0, 'completed_at': datetime.utcnow()},
        {'actual_duration_ms': 2500.0, 'completed_at': datetime.utcnow()},
        {'actual_duration_ms': 3000.0, 'completed_at': datetime.utcnow()},
    ]

    # Collection mockada
    mock_collection = AsyncMock()
    mock_collection.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=completions
    )
    mock_collection.count_documents = AsyncMock(return_value=3)  # Queue depth

    mock.db = {'execution_tickets': mock_collection}
    return mock


@pytest.fixture
def redis_client():
    """Redis mockado."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock()
    return mock


@pytest.fixture
def optimizer_client():
    """Optimizer gRPC client mockado."""
    mock = AsyncMock()
    mock.get_load_forecast = AsyncMock(return_value={
        'forecast': [
            {'timestamp': 1234567890, 'value': 40.0},
            {'timestamp': 1234567920, 'value': 45.0}
        ]
    })
    mock.get_scheduling_recommendation = AsyncMock(return_value={
        'action': 'SCALE_UP',
        'confidence': 0.85
    })
    return mock


@pytest.fixture
def kafka_producer():
    """Kafka producer mockado."""
    mock = AsyncMock()
    mock.send = AsyncMock(return_value={'published': True, 'offset': 123})
    return mock


@pytest.fixture
def service_registry_client():
    """Service Registry client mockado."""
    mock = AsyncMock()
    mock.discover_agents = AsyncMock(return_value=[
        {
            'agent_id': 'worker-1',
            'agent_type': 'deployment-agent',
            'status': 'HEALTHY',
            'telemetry': {
                'success_rate': 0.95,
                'avg_duration_ms': 2000,
                'total_executions': 100
            }
        },
        {
            'agent_id': 'worker-2',
            'agent_type': 'deployment-agent',
            'status': 'HEALTHY',
            'telemetry': {
                'success_rate': 0.90,
                'avg_duration_ms': 2500,
                'total_executions': 80
            }
        }
    ])
    return mock


@pytest.fixture
def metrics():
    """Métricas mockadas."""
    return Mock(spec=OrchestratorMetrics)


@pytest.fixture
async def integrated_components(
    config,
    mongodb_client_with_data,
    redis_client,
    optimizer_client,
    kafka_producer,
    service_registry_client,
    metrics
):
    """Stack completo de componentes integrados."""
    # LoadPredictor
    load_predictor = LoadPredictor(
        config=config,
        mongodb_client=mongodb_client_with_data,
        redis_client=redis_client,
        metrics=metrics
    )

    # SchedulingOptimizer
    scheduling_optimizer = SchedulingOptimizer(
        config=config,
        optimizer_client=optimizer_client,
        local_predictor=load_predictor,
        kafka_producer=kafka_producer,
        metrics=metrics
    )

    # ResourceAllocator
    resource_allocator = ResourceAllocator(
        registry_client=service_registry_client,
        config=config,
        metrics=metrics,
        scheduling_optimizer=scheduling_optimizer
    )

    return {
        'load_predictor': load_predictor,
        'scheduling_optimizer': scheduling_optimizer,
        'resource_allocator': resource_allocator
    }


class TestMLSchedulingIntegration:
    """Testes de integração end-to-end do ML scheduling."""

    @pytest.mark.asyncio
    async def test_full_scheduling_flow_with_ml_optimization(
        self,
        integrated_components,
        service_registry_client
    ):
        """Testa fluxo completo de scheduling com otimização ML."""
        allocator = integrated_components['resource_allocator']

        ticket = {
            'ticket_id': 'ticket-integration-1',
            'task_type': 'deployment',
            'required_capabilities': ['deployment'],
            'namespace': 'default',
            'security_level': 'standard'
        }

        # Descobrir workers
        workers = await allocator.discover_workers(ticket)
        assert len(workers) == 2

        # Selecionar melhor worker (com ML optimization)
        best_worker = await allocator.select_best_worker(
            workers=workers,
            priority_score=0.7,
            ticket=ticket
        )

        assert best_worker is not None
        assert 'agent_id' in best_worker
        assert best_worker['ml_enriched'] is True
        assert 'predicted_queue_ms' in best_worker
        assert 'predicted_load_pct' in best_worker
        assert 'rl_boost' in best_worker

    @pytest.mark.asyncio
    async def test_ml_predictions_enrich_worker_scoring(
        self,
        integrated_components
    ):
        """Testa que predições ML influenciam scoring de workers."""
        optimizer = integrated_components['scheduling_optimizer']
        allocator = integrated_components['resource_allocator']

        # Workers com diferentes cargas preditas
        workers = [
            {
                'agent_id': 'worker-low-load',
                'status': 'HEALTHY',
                'telemetry': {'success_rate': 0.95, 'avg_duration_ms': 2000, 'total_executions': 100}
            },
            {
                'agent_id': 'worker-high-load',
                'status': 'HEALTHY',
                'telemetry': {'success_rate': 0.95, 'avg_duration_ms': 2000, 'total_executions': 100}
            }
        ]

        ticket = {'ticket_id': 'ticket-1', 'task_type': 'deployment'}

        # Enriquecer com ML
        enriched = await optimizer.optimize_allocation(
            ticket=ticket,
            workers=workers
        )

        # Selecionar melhor worker
        best_worker = await allocator.select_best_worker(
            workers=enriched,
            priority_score=0.7,
            ticket=ticket
        )

        # Verificar que RL boost foi aplicado (SCALE_UP prefere baixa carga)
        assert best_worker is not None
        # Worker com RL boost deve ter score mais alto
        assert best_worker.get('rl_boost', 1.0) >= 1.0

    @pytest.mark.asyncio
    async def test_fallback_to_local_when_optimizer_unavailable(
        self,
        config,
        mongodb_client_with_data,
        redis_client,
        kafka_producer,
        service_registry_client,
        metrics
    ):
        """Testa fallback para predições locais quando optimizer remoto falha."""
        # Optimizer que falha
        failing_optimizer = AsyncMock()
        failing_optimizer.get_scheduling_recommendation.side_effect = Exception("Connection error")

        # Stack com optimizer falhando
        load_predictor = LoadPredictor(
            config=config,
            mongodb_client=mongodb_client_with_data,
            redis_client=redis_client,
            metrics=metrics
        )

        scheduling_optimizer = SchedulingOptimizer(
            config=config,
            optimizer_client=failing_optimizer,
            local_predictor=load_predictor,
            kafka_producer=kafka_producer,
            metrics=metrics
        )

        resource_allocator = ResourceAllocator(
            registry_client=service_registry_client,
            config=config,
            metrics=metrics,
            scheduling_optimizer=scheduling_optimizer
        )

        ticket = {'ticket_id': 'ticket-2', 'task_type': 'testing'}
        workers = await resource_allocator.discover_workers(ticket)

        # Deve funcionar mesmo com optimizer falh ando (usa predições locais)
        best_worker = await resource_allocator.select_best_worker(
            workers=workers,
            priority_score=0.6,
            ticket=ticket
        )

        assert best_worker is not None
        assert best_worker['ml_enriched'] is True  # Ainda tem enrichment local

    @pytest.mark.asyncio
    async def test_degraded_mode_without_mongodb(
        self,
        config,
        redis_client,
        optimizer_client,
        kafka_producer,
        service_registry_client,
        metrics
    ):
        """Testa modo degradado sem MongoDB (usa defaults)."""
        # Stack sem MongoDB
        load_predictor = LoadPredictor(
            config=config,
            mongodb_client=None,  # MongoDB indisponível
            redis_client=redis_client,
            metrics=metrics
        )

        scheduling_optimizer = SchedulingOptimizer(
            config=config,
            optimizer_client=optimizer_client,
            local_predictor=load_predictor,
            kafka_producer=kafka_producer,
            metrics=metrics
        )

        resource_allocator = ResourceAllocator(
            registry_client=service_registry_client,
            config=config,
            metrics=metrics,
            scheduling_optimizer=scheduling_optimizer
        )

        ticket = {'ticket_id': 'ticket-3', 'task_type': 'validation'}
        workers = await resource_allocator.discover_workers(ticket)

        # Deve funcionar em modo degradado
        best_worker = await resource_allocator.select_best_worker(
            workers=workers,
            priority_score=0.8,
            ticket=ticket
        )

        assert best_worker is not None
        # Predições devem usar defaults
        assert best_worker.get('predicted_queue_ms') in [1000.0, 2000.0]  # Defaults
        assert best_worker.get('predicted_load_pct') == 0.5  # Default

    @pytest.mark.asyncio
    async def test_allocation_outcome_feedback_loop(
        self,
        integrated_components,
        kafka_producer
    ):
        """Testa feedback loop de allocation outcomes para RL training."""
        optimizer = integrated_components['scheduling_optimizer']

        ticket = {
            'ticket_id': 'ticket-feedback',
            'status': 'COMPLETED',
            'risk_band': 'high',
            'priority_score': 0.9
        }

        worker = {
            'agent_id': 'worker-selected',
            'predicted_queue_ms': 2000.0,
            'predicted_load_pct': 0.45,
            'ml_enriched': True
        }

        await optimizer.record_allocation_outcome(
            ticket=ticket,
            worker=worker,
            actual_duration_ms=2200.0
        )

        # Verificar que outcome foi publicado no Kafka
        kafka_producer.send.assert_called_once()
        call_args = kafka_producer.send.call_args

        outcome = call_args[1]['value']
        assert outcome['ticket_id'] == 'ticket-feedback'
        assert outcome['worker_id'] == 'worker-selected'
        assert outcome['predicted_queue_ms'] == 2000.0
        assert outcome['actual_duration_ms'] == 2200.0
        assert outcome['success'] is True

    @pytest.mark.asyncio
    async def test_metrics_recorded_throughout_pipeline(
        self,
        integrated_components,
        metrics
    ):
        """Testa que métricas são registradas em todos os estágios."""
        allocator = integrated_components['resource_allocator']

        ticket = {'ticket_id': 'ticket-metrics', 'task_type': 'deployment'}
        workers = await allocator.discover_workers(ticket)
        best_worker = await allocator.select_best_worker(
            workers=workers,
            priority_score=0.75,
            ticket=ticket
        )

        # Verificar chamadas de métricas ao longo do pipeline
        assert metrics.record_ml_prediction.called
        assert metrics.record_predicted_queue_time.called
        assert metrics.record_predicted_worker_load.called
        assert metrics.record_ml_optimization.called
