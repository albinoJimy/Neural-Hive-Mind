"""
Testes de integração para OptimizerGrpcClient e IntelligentScheduler.

Testa conexão gRPC, forecasts, recomendações, fallback, cache, timeout,
e integração com intelligent scheduler.
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import grpc

from src.clients.optimizer_grpc_client import OptimizerGrpcClient
from src.scheduler.intelligent_scheduler import IntelligentScheduler
from src.config.settings import OrchestratorSettings


# Fixtures

@pytest.fixture
def mock_config():
    """Mock de configuração."""
    config = Mock(spec=OrchestratorSettings)
    config.optimizer_agents_endpoint = 'localhost:50051'
    config.service_registry_cache_ttl_seconds = 60
    return config


@pytest.fixture
def mock_metrics():
    """Mock de métricas."""
    metrics = Mock()
    metrics.record_priority_score = Mock()
    metrics.record_workers_discovered = Mock()
    metrics.record_scheduler_allocation = Mock()
    metrics.record_scheduler_rejection = Mock()
    metrics.record_cache_hit = Mock()
    metrics.record_discovery_failure = Mock()
    return metrics


@pytest.fixture
def mock_priority_calculator():
    """Mock de PriorityCalculator."""
    calculator = Mock()
    calculator.calculate_priority_score = Mock(return_value=0.75)
    return calculator


@pytest.fixture
def mock_resource_allocator():
    """Mock de ResourceAllocator."""
    allocator = AsyncMock()
    allocator.discover_workers = AsyncMock(return_value=[
        {
            'agent_id': 'worker-1',
            'agent_type': 'worker-agent',
            'score': 0.85,
            'capabilities': ['python', 'docker']
        }
    ])
    allocator.select_best_worker = Mock(return_value={
        'agent_id': 'worker-1',
        'agent_type': 'worker-agent',
        'score': 0.85
    })
    return allocator


@pytest.fixture
def sample_ticket():
    """Ticket de exemplo."""
    return {
        'ticket_id': 'test-ticket-123',
        'task_type': 'BUILD',
        'risk_band': 'high',
        'required_capabilities': ['python', 'docker'],
        'qos': {'delivery_guarantee': 'exactly_once'},
        'sla': {'timeout_ms': 300000},
        'namespace': 'production',
        'security_level': 'standard',
        'estimated_duration_ms': 120000
    }


# Tests - OptimizerGrpcClient

@pytest.mark.asyncio
class TestOptimizerGrpcClient:
    """Testes de integração do OptimizerGrpcClient."""

    async def test_initialize_success(self, mock_config):
        """Testa inicialização bem-sucedida."""
        client = OptimizerGrpcClient(mock_config)

        with patch('grpc.aio.insecure_channel') as mock_channel:
            mock_channel_instance = AsyncMock()
            mock_channel_instance.channel_ready = AsyncMock()
            mock_channel.return_value = mock_channel_instance

            with patch('src.clients.optimizer_grpc_client.optimizer_agent_pb2_grpc'):
                await client.initialize()

            assert client.channel is not None
            assert client.stub is not None

    async def test_initialize_proto_not_found(self, mock_config):
        """Testa inicialização quando proto não está disponível."""
        client = OptimizerGrpcClient(mock_config)

        with patch('src.clients.optimizer_grpc_client.optimizer_agent_pb2', None):
            with patch('src.clients.optimizer_grpc_client.optimizer_agent_pb2_grpc', None):
                await client.initialize()

            # Não deve falhar, apenas log warning
            assert client.stub is None

    async def test_get_load_forecast_success(self, mock_config):
        """Testa obtenção de forecast bem-sucedida."""
        client = OptimizerGrpcClient(mock_config)

        # Mock stub gRPC
        mock_stub = AsyncMock()
        mock_response = Mock()
        mock_response.forecast = [
            Mock(
                timestamp='2024-01-01T12:00:00Z',
                ticket_count=100,
                resource_demand=Mock(cpu_cores=10.0, memory_mb=10000),
                confidence_lower=90,
                confidence_upper=110
            )
        ]
        mock_response.metadata = Mock(
            model_horizon=60,
            horizon_requested=60,
            forecast_generated_at='2024-01-01T11:00:00Z',
            data_points_used=1000,
            confidence_level=0.95
        )
        mock_stub.GetLoadForecast = AsyncMock(return_value=mock_response)

        client.stub = mock_stub

        with patch('src.clients.optimizer_grpc_client.optimizer_agent_pb2') as mock_proto:
            mock_proto.LoadForecastRequest = Mock

            forecast = await client.get_load_forecast(
                horizon_minutes=60,
                include_confidence_intervals=True
            )

        assert forecast is not None
        assert 'forecast' in forecast
        assert 'metadata' in forecast
        assert len(forecast['forecast']) == 1
        assert forecast['forecast'][0]['ticket_count'] == 100

    async def test_get_load_forecast_timeout(self, mock_config):
        """Testa timeout em forecast."""
        client = OptimizerGrpcClient(mock_config)

        # Mock stub que demora muito
        mock_stub = AsyncMock()
        mock_stub.GetLoadForecast = AsyncMock(
            side_effect=grpc.RpcError()
        )
        client.stub = mock_stub

        with patch('src.clients.optimizer_grpc_client.optimizer_agent_pb2') as mock_proto:
            mock_proto.LoadForecastRequest = Mock

            forecast = await client.get_load_forecast(horizon_minutes=60)

        # Deve retornar None em caso de erro
        assert forecast is None

    async def test_get_load_forecast_stub_not_initialized(self, mock_config):
        """Testa forecast sem stub inicializado."""
        client = OptimizerGrpcClient(mock_config)
        client.stub = None

        forecast = await client.get_load_forecast(horizon_minutes=60)

        assert forecast is None

    async def test_get_scheduling_recommendation_success(self, mock_config):
        """Testa obtenção de recomendação bem-sucedida."""
        client = OptimizerGrpcClient(mock_config)

        # Mock stub gRPC
        mock_stub = AsyncMock()
        mock_response = Mock(
            action='INCREASE_WORKER_POOL',
            justification='High utilization detected',
            expected_improvement=0.15,
            risk_score=0.25,
            confidence=0.85
        )
        mock_stub.GetSchedulingRecommendation = AsyncMock(return_value=mock_response)

        client.stub = mock_stub

        with patch('src.clients.optimizer_grpc_client.optimizer_agent_pb2') as mock_proto:
            mock_proto.SchedulingRecommendationRequest = Mock

            current_state = {
                'current_load': 100,
                'worker_utilization': 0.85,
                'queue_depth': 50,
                'sla_compliance': 0.90
            }

            recommendation = await client.get_scheduling_recommendation(current_state)

        assert recommendation is not None
        assert recommendation['action'] == 'INCREASE_WORKER_POOL'
        assert recommendation['confidence'] == 0.85

    async def test_get_scheduling_recommendation_grpc_error(self, mock_config):
        """Testa erro gRPC em recomendação."""
        client = OptimizerGrpcClient(mock_config)

        mock_stub = AsyncMock()
        mock_stub.GetSchedulingRecommendation = AsyncMock(
            side_effect=grpc.RpcError()
        )
        client.stub = mock_stub

        with patch('src.clients.optimizer_grpc_client.optimizer_agent_pb2') as mock_proto:
            mock_proto.SchedulingRecommendationRequest = Mock

            recommendation = await client.get_scheduling_recommendation({})

        assert recommendation is None

    async def test_close(self, mock_config):
        """Testa fechamento de canal."""
        client = OptimizerGrpcClient(mock_config)

        mock_channel = AsyncMock()
        mock_channel.close = AsyncMock()
        client.channel = mock_channel

        await client.close()

        mock_channel.close.assert_called_once()


# Tests - IntelligentScheduler com Optimizer Integration

@pytest.mark.asyncio
class TestIntelligentSchedulerOptimizerIntegration:
    """Testes de integração do scheduler com optimizer."""

    async def test_schedule_ticket_with_ml_predictions(
        self,
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        sample_ticket
    ):
        """Testa scheduling com predições ML."""
        scheduler = IntelligentScheduler(
            mock_config,
            mock_metrics,
            mock_priority_calculator,
            mock_resource_allocator
        )

        # Ticket com predições ML
        ticket_with_ml = {
            **sample_ticket,
            'predictions': {
                'duration_ms': 150000,  # 50% maior que estimativa
                'anomaly': {'is_anomaly': False}
            }
        }

        result = await scheduler.schedule_ticket(ticket_with_ml)

        assert 'allocation_metadata' in result
        assert result['allocation_metadata']['agent_id'] == 'worker-1'
        # Prioridade deve ter sido boosted
        assert result['allocation_metadata']['priority_score'] >= 0.75

    async def test_schedule_ticket_optimizer_unavailable_fallback(
        self,
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        sample_ticket
    ):
        """Testa fallback quando optimizer indisponível."""
        scheduler = IntelligentScheduler(
            mock_config,
            mock_metrics,
            mock_priority_calculator,
            mock_resource_allocator
        )

        # Resource allocator retorna vazio (optimizer down)
        mock_resource_allocator.discover_workers = AsyncMock(return_value=[])

        result = await scheduler.schedule_ticket(sample_ticket)

        # Deve usar fallback allocation
        assert 'allocation_metadata' in result
        assert result['allocation_metadata']['allocation_method'] == 'fallback_stub'
        assert result['allocation_metadata']['agent_id'] == 'worker-agent-pool'
        mock_metrics.record_scheduler_rejection.assert_called_with('no_workers')

    async def test_schedule_ticket_cache_behavior(
        self,
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        sample_ticket
    ):
        """Testa comportamento de cache de descoberta."""
        scheduler = IntelligentScheduler(
            mock_config,
            mock_metrics,
            mock_priority_calculator,
            mock_resource_allocator
        )

        # Primeira chamada - cache miss
        await scheduler.schedule_ticket(sample_ticket)
        assert mock_resource_allocator.discover_workers.call_count == 1

        # Segunda chamada com mesmo ticket - cache hit
        await scheduler.schedule_ticket(sample_ticket)
        assert mock_resource_allocator.discover_workers.call_count == 1  # Não aumentou
        mock_metrics.record_cache_hit.assert_called()

    async def test_schedule_ticket_discovery_timeout(
        self,
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        sample_ticket
    ):
        """Testa timeout em descoberta de workers."""
        scheduler = IntelligentScheduler(
            mock_config,
            mock_metrics,
            mock_priority_calculator,
            mock_resource_allocator
        )

        # Simular timeout
        import asyncio

        async def slow_discover(*args, **kwargs):
            await asyncio.sleep(10)
            return []

        mock_resource_allocator.discover_workers = slow_discover

        result = await scheduler.schedule_ticket(sample_ticket)

        # Deve usar fallback após timeout
        assert result['allocation_metadata']['allocation_method'] == 'fallback_stub'
        mock_metrics.record_discovery_failure.assert_called_with('timeout')

    async def test_schedule_ticket_invalid_ml_predictions_rejection(
        self,
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator
    ):
        """Testa rejeição de predições ML inválidas."""
        scheduler = IntelligentScheduler(
            mock_config,
            mock_metrics,
            mock_priority_calculator,
            mock_resource_allocator
        )

        # Ticket com predições inválidas
        invalid_ticket = {
            'ticket_id': 'invalid-123',
            'task_type': 'BUILD',
            'risk_band': 'high',
            'required_capabilities': [],
            'qos': {},
            'sla': {},
            'predictions': {
                'duration_ms': -1000,  # Inválido
                'anomaly': {'is_anomaly': True}
            }
        }

        result = await scheduler.schedule_ticket(invalid_ticket)

        # Deve ignorar predições inválidas mas ainda alocar
        assert 'allocation_metadata' in result

    async def test_schedule_ticket_metadata_enrichment(
        self,
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        sample_ticket
    ):
        """Testa enriquecimento de metadata com ML."""
        scheduler = IntelligentScheduler(
            mock_config,
            mock_metrics,
            mock_priority_calculator,
            mock_resource_allocator
        )

        # Ticket com predições e anomalia
        ticket_with_anomaly = {
            **sample_ticket,
            'predictions': {
                'duration_ms': 180000,
                'anomaly': {'is_anomaly': True, 'score': 0.95}
            }
        }

        result = await scheduler.schedule_ticket(ticket_with_anomaly)

        metadata = result['allocation_metadata']
        assert 'predicted_duration_ms' in metadata
        assert metadata['predicted_duration_ms'] == 180000
        assert 'anomaly_detected' in metadata
        assert metadata['anomaly_detected'] is True

    async def test_schedule_ticket_latency_measurement(
        self,
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        sample_ticket
    ):
        """Testa medição de latência de scheduling."""
        scheduler = IntelligentScheduler(
            mock_config,
            mock_metrics,
            mock_priority_calculator,
            mock_resource_allocator
        )

        await scheduler.schedule_ticket(sample_ticket)

        # Verificar que latência foi registrada
        mock_metrics.record_scheduler_allocation.assert_called()
        call_args = mock_metrics.record_scheduler_allocation.call_args[1]
        assert 'duration_seconds' in call_args
        assert call_args['duration_seconds'] > 0
        assert call_args['status'] == 'success'
        assert call_args['fallback'] is False


# Tests End-to-End

@pytest.mark.asyncio
class TestOptimizerEndToEnd:
    """Testes end-to-end do fluxo completo."""

    async def test_full_flow_with_forecast_and_recommendation(
        self,
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        sample_ticket
    ):
        """Testa fluxo completo: forecast -> recomendação -> scheduling."""
        # Setup optimizer client
        optimizer_client = OptimizerGrpcClient(mock_config)

        # Mock forecast
        mock_stub = AsyncMock()
        mock_forecast_response = Mock()
        mock_forecast_response.forecast = [
            Mock(timestamp='2024-01-01T12:00:00Z', ticket_count=150 + i, resource_demand=Mock(cpu_cores=15, memory_mb=15000))
            for i in range(60)
        ]
        mock_forecast_response.metadata = Mock(
            model_horizon=60, horizon_requested=60, forecast_generated_at='2024-01-01T11:00:00Z',
            data_points_used=5000, confidence_level=0.95
        )

        # Mock recommendation
        mock_recommendation_response = Mock(
            action='PREEMPTIVE_SCALING',
            justification='Spike predicted in next hour',
            expected_improvement=0.20,
            risk_score=0.25,
            confidence=0.90
        )

        mock_stub.GetLoadForecast = AsyncMock(return_value=mock_forecast_response)
        mock_stub.GetSchedulingRecommendation = AsyncMock(return_value=mock_recommendation_response)

        optimizer_client.stub = mock_stub

        # Setup scheduler
        scheduler = IntelligentScheduler(
            mock_config,
            mock_metrics,
            mock_priority_calculator,
            mock_resource_allocator
        )

        with patch('src.clients.optimizer_grpc_client.optimizer_agent_pb2') as mock_proto:
            mock_proto.LoadForecastRequest = Mock
            mock_proto.SchedulingRecommendationRequest = Mock

            # 1. Obter forecast
            forecast = await optimizer_client.get_load_forecast(horizon_minutes=60, include_confidence_intervals=True)
            assert forecast is not None
            assert len(forecast['forecast']) == 60

            # 2. Obter recomendação
            current_state = {
                'current_load': 100,
                'worker_utilization': 0.75,
                'queue_depth': 30,
                'sla_compliance': 0.92
            }
            recommendation = await optimizer_client.get_scheduling_recommendation(current_state)
            assert recommendation is not None
            assert recommendation['action'] == 'PREEMPTIVE_SCALING'

            # 3. Agendar ticket
            result = await scheduler.schedule_ticket(sample_ticket)
            assert 'allocation_metadata' in result
            assert result['allocation_metadata']['allocation_method'] == 'intelligent_scheduler'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
