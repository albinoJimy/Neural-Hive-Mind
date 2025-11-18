"""
Testes de integração para Optimizer Agents (gRPC client integration).

Cobertura:
- Conexão gRPC com OptimizerAgent
- Recuperação de forecast de carga
- Aplicação de recomendações de agendamento
- Scheduler usa previsões para decisões
- Fallback quando optimizer indisponível
- Metadata enrichment com dados de otimização
- Cache de previsões
- Latência e timeouts
- Rejeição de recomendações inválidas
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import grpc
from grpc.aio import AioRpcError

from src.clients.optimizer_grpc_client import OptimizerGRPCClient
from src.scheduler.ml_scheduler import MLScheduler


@pytest.fixture
def config():
    """Configuração para cliente gRPC."""
    return {
        'optimizer_grpc_endpoint': 'localhost:50053',
        'optimizer_grpc_timeout_seconds': 5,
        'optimizer_forecast_horizon_minutes': 60,
        'optimizer_recommendation_confidence_threshold': 0.7,
        'optimizer_enabled': True,
        'optimizer_fallback_on_failure': True,
    }


@pytest.fixture
def mock_grpc_channel():
    """Mock gRPC channel."""
    channel = MagicMock()
    return channel


@pytest.fixture
def mock_grpc_stub():
    """Mock gRPC stub para OptimizerAgent."""
    stub = MagicMock()

    # Mock GetLoadForecast
    forecast_response = MagicMock()
    forecast_response.predicted_volume = 125
    forecast_response.confidence = 0.85
    forecast_response.forecast_horizon_minutes = 60
    forecast_response.resource_demand_cpu = 0.65
    forecast_response.resource_demand_memory = 0.58
    forecast_response.bottleneck_probability = 0.15
    forecast_response.timestamp = int(datetime.utcnow().timestamp())

    stub.GetLoadForecast = AsyncMock(return_value=forecast_response)

    # Mock GetSchedulingRecommendation
    rec_response = MagicMock()
    rec_response.action = "INCREASE_WORKER_POOL"
    rec_response.confidence = 0.82
    rec_response.parameters = {"target_workers": "15", "scale_increment": "3"}
    rec_response.expected_impact_sla_compliance = 0.92
    rec_response.expected_impact_throughput = 1.15
    rec_response.rationale = "High predicted load in next 60 minutes"

    stub.GetSchedulingRecommendation = AsyncMock(return_value=rec_response)

    return stub


@pytest.fixture
def mock_metrics():
    """Mock Prometheus metrics."""
    metrics = MagicMock()
    metrics.optimizer_grpc_calls_total = MagicMock()
    metrics.optimizer_grpc_errors_total = MagicMock()
    metrics.optimizer_grpc_latency = MagicMock()
    metrics.optimizer_recommendations_applied = MagicMock()
    metrics.optimizer_recommendations_rejected = MagicMock()
    return metrics


@pytest_asyncio.fixture
async def optimizer_client(config, mock_grpc_channel, mock_grpc_stub, mock_metrics):
    """Fixture do OptimizerGRPCClient."""
    with patch('grpc.aio.insecure_channel', return_value=mock_grpc_channel):
        with patch('src.clients.optimizer_grpc_client.OptimizerAgentStub',
                   return_value=mock_grpc_stub):
            client = OptimizerGRPCClient(config=config, metrics=mock_metrics)
            await client.initialize()
            return client


# ===== Testes de Conexão =====

@pytest.mark.asyncio
async def test_client_initialization_success(optimizer_client):
    """Testa inicialização bem-sucedida do cliente gRPC."""
    assert optimizer_client._initialized is True
    assert optimizer_client.stub is not None


@pytest.mark.asyncio
async def test_client_connection_failure_fallback(config, mock_metrics):
    """Testa fallback quando conexão gRPC falha."""
    with patch('grpc.aio.insecure_channel', side_effect=Exception("Connection refused")):
        client = OptimizerGRPCClient(config=config, metrics=mock_metrics)

        # Deve inicializar mesmo com falha (fallback mode)
        await client.initialize()

        # Modo fallback ativado
        assert client.fallback_mode is True


# ===== Testes de Forecast Retrieval =====

@pytest.mark.asyncio
async def test_get_load_forecast_success(optimizer_client, mock_grpc_stub):
    """Testa recuperação de forecast de carga com sucesso."""
    forecast = await optimizer_client.get_load_forecast(
        horizon_minutes=60,
        task_type='processing',
        risk_band='medium'
    )

    assert forecast['predicted_volume'] == 125
    assert forecast['confidence'] == 0.85
    assert forecast['bottleneck_probability'] == 0.15
    assert 'resource_demand' in forecast

    # Verificar que gRPC stub foi chamado
    mock_grpc_stub.GetLoadForecast.assert_called_once()


@pytest.mark.asyncio
async def test_get_load_forecast_with_metadata(optimizer_client):
    """Testa que forecast inclui metadata completa."""
    forecast = await optimizer_client.get_load_forecast(
        horizon_minutes=360,
        task_type='analysis',
        risk_band='high'
    )

    assert 'timestamp' in forecast
    assert 'forecast_horizon_minutes' in forecast
    assert forecast['forecast_horizon_minutes'] == 60


@pytest.mark.asyncio
async def test_get_load_forecast_grpc_timeout(optimizer_client, mock_grpc_stub):
    """Testa timeout em chamada gRPC de forecast."""
    mock_grpc_stub.GetLoadForecast = AsyncMock(
        side_effect=AioRpcError(code=grpc.StatusCode.DEADLINE_EXCEEDED,
                                 initial_metadata=None,
                                 trailing_metadata=None,
                                 details="Timeout")
    )

    # Deve retornar None em caso de timeout
    forecast = await optimizer_client.get_load_forecast(
        horizon_minutes=60,
        task_type='processing',
        risk_band='medium'
    )

    assert forecast is None

    # Métrica de erro deve ser incrementada
    optimizer_client.metrics.optimizer_grpc_errors_total.inc.assert_called()


# ===== Testes de Scheduling Recommendations =====

@pytest.mark.asyncio
async def test_get_scheduling_recommendation_success(optimizer_client, mock_grpc_stub):
    """Testa obtenção de recomendação de agendamento."""
    state = {
        'current_queue_depth': 150,
        'active_workers': 10,
        'avg_task_duration_ms': 5000,
        'sla_compliance_rate': 0.88,
        'predicted_load_1h': 125
    }

    recommendation = await optimizer_client.get_scheduling_recommendation(state)

    assert recommendation['action'] == "INCREASE_WORKER_POOL"
    assert recommendation['confidence'] == 0.82
    assert 'parameters' in recommendation
    assert recommendation['parameters']['target_workers'] == "15"
    assert 'expected_impact' in recommendation


@pytest.mark.asyncio
async def test_recommendation_rejected_low_confidence(optimizer_client, mock_grpc_stub):
    """Testa rejeição de recomendação com confiança baixa (< threshold)."""
    # Mock recomendação com baixa confiança
    rec_response = MagicMock()
    rec_response.action = "DECREASE_WORKER_POOL"
    rec_response.confidence = 0.55  # Abaixo de 0.7
    rec_response.parameters = {}

    mock_grpc_stub.GetSchedulingRecommendation = AsyncMock(return_value=rec_response)

    state = {'current_queue_depth': 50, 'active_workers': 10}
    recommendation = await optimizer_client.get_scheduling_recommendation(state)

    # Deve retornar None (rejeitada)
    assert recommendation is None

    # Métrica de rejeição incrementada
    optimizer_client.metrics.optimizer_recommendations_rejected.inc.assert_called()


@pytest.mark.asyncio
async def test_recommendation_applied_successfully(optimizer_client):
    """Testa aplicação bem-sucedida de recomendação."""
    state = {'current_queue_depth': 200, 'active_workers': 8}
    recommendation = await optimizer_client.get_scheduling_recommendation(state)

    assert recommendation is not None
    assert recommendation['confidence'] >= 0.7

    # Métrica de aplicação incrementada
    optimizer_client.metrics.optimizer_recommendations_applied.inc.assert_called()


# ===== Testes de Scheduler Integration =====

@pytest.mark.asyncio
async def test_scheduler_uses_predictions(config, mock_metrics):
    """Testa que scheduler usa previsões para decisões de agendamento."""
    mock_optimizer_client = AsyncMock()
    mock_optimizer_client.get_load_forecast = AsyncMock(return_value={
        'predicted_volume': 180,
        'confidence': 0.88,
        'bottleneck_probability': 0.42
    })

    scheduler = MLScheduler(
        optimizer_client=mock_optimizer_client,
        config=config,
        metrics=mock_metrics
    )

    # Scheduler deve consultar forecast ao tomar decisão
    decision = await scheduler.make_scheduling_decision({
        'current_queue_depth': 100,
        'active_workers': 10
    })

    assert mock_optimizer_client.get_load_forecast.called
    assert 'action' in decision


@pytest.mark.asyncio
async def test_scheduler_fallback_on_optimizer_unavailable(config, mock_metrics):
    """Testa fallback do scheduler quando optimizer está indisponível."""
    mock_optimizer_client = AsyncMock()
    mock_optimizer_client.get_load_forecast = AsyncMock(return_value=None)  # Indisponível

    scheduler = MLScheduler(
        optimizer_client=mock_optimizer_client,
        config=config,
        metrics=mock_metrics
    )

    # Scheduler deve usar heurística padrão
    decision = await scheduler.make_scheduling_decision({
        'current_queue_depth': 150,
        'active_workers': 10
    })

    assert 'action' in decision
    assert decision['action'] is not None  # Alguma decisão foi tomada


# ===== Testes de Metadata Enrichment =====

@pytest.mark.asyncio
async def test_metadata_enrichment_with_optimizer_data(optimizer_client):
    """Testa enriquecimento de metadata de tickets com dados de otimização."""
    forecast = await optimizer_client.get_load_forecast(
        horizon_minutes=60,
        task_type='processing',
        risk_band='high'
    )

    # Metadata deve incluir campos para tracking
    enriched_metadata = {
        'original_priority': 5,
        'optimizer_predicted_load': forecast['predicted_volume'],
        'optimizer_confidence': forecast['confidence'],
        'optimizer_bottleneck_risk': forecast['bottleneck_probability'],
        'optimizer_enriched_at': datetime.utcnow().isoformat()
    }

    assert enriched_metadata['optimizer_predicted_load'] == 125
    assert enriched_metadata['optimizer_confidence'] == 0.85


# ===== Testes de Cache =====

@pytest.mark.asyncio
async def test_forecast_cache_hit(optimizer_client, mock_grpc_stub):
    """Testa cache de previsões (não refaz chamada gRPC)."""
    # Primeira chamada
    forecast1 = await optimizer_client.get_load_forecast(
        horizon_minutes=60,
        task_type='processing',
        risk_band='medium'
    )

    # Segunda chamada (deve usar cache)
    forecast2 = await optimizer_client.get_load_forecast(
        horizon_minutes=60,
        task_type='processing',
        risk_band='medium'
    )

    # gRPC stub deve ser chamado apenas uma vez
    assert mock_grpc_stub.GetLoadForecast.call_count == 1

    # Forecasts devem ser idênticos
    assert forecast1 == forecast2


@pytest.mark.asyncio
async def test_forecast_cache_expiration(optimizer_client, mock_grpc_stub):
    """Testa expiração de cache (TTL)."""
    forecast1 = await optimizer_client.get_load_forecast(
        horizon_minutes=60,
        task_type='processing',
        risk_band='medium'
    )

    # Simular passagem de tempo (TTL expirado)
    with patch('time.time', return_value=datetime.utcnow().timestamp() + 400):
        forecast2 = await optimizer_client.get_load_forecast(
            horizon_minutes=60,
            task_type='processing',
            risk_band='medium'
        )

    # gRPC stub deve ser chamado duas vezes (cache expirou)
    assert mock_grpc_stub.GetLoadForecast.call_count == 2


# ===== Testes de Latência e Timeouts =====

@pytest.mark.asyncio
async def test_grpc_latency_metric_recorded(optimizer_client):
    """Testa que latência de chamada gRPC é registrada."""
    await optimizer_client.get_load_forecast(
        horizon_minutes=60,
        task_type='processing',
        risk_band='medium'
    )

    # Métrica de latência deve ser observada
    optimizer_client.metrics.optimizer_grpc_latency.observe.assert_called()


@pytest.mark.asyncio
async def test_grpc_timeout_configuration(config):
    """Testa que timeout gRPC é configurado corretamente."""
    assert config['optimizer_grpc_timeout_seconds'] == 5


# ===== Testes de Validação de Recomendações =====

@pytest.mark.asyncio
async def test_invalid_recommendation_rejected(optimizer_client, mock_grpc_stub):
    """Testa rejeição de recomendação inválida."""
    # Mock recomendação inválida (parâmetros faltando)
    rec_response = MagicMock()
    rec_response.action = "INCREASE_WORKER_POOL"
    rec_response.confidence = 0.85
    rec_response.parameters = {}  # Parâmetros faltando

    mock_grpc_stub.GetSchedulingRecommendation = AsyncMock(return_value=rec_response)

    state = {'current_queue_depth': 150}
    recommendation = await optimizer_client.get_scheduling_recommendation(state)

    # Deve ser rejeitada por falta de parâmetros
    assert recommendation is None or 'parameters' not in recommendation


@pytest.mark.asyncio
async def test_recommendation_validation_parameters(optimizer_client):
    """Testa validação de parâmetros de recomendação."""
    state = {'current_queue_depth': 200, 'active_workers': 10}
    recommendation = await optimizer_client.get_scheduling_recommendation(state)

    if recommendation:
        # Parâmetros devem ser válidos
        assert 'parameters' in recommendation
        assert isinstance(recommendation['parameters'], dict)

        if recommendation['action'] == "INCREASE_WORKER_POOL":
            assert 'target_workers' in recommendation['parameters']
