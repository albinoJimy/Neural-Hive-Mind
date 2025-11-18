"""
Testes unitários para SchedulingOptimizer (orquestrador ML de scheduling).
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.ml.scheduling_optimizer import SchedulingOptimizer
from src.ml.load_predictor import LoadPredictor
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
def mock_config():
    """Configuração mockada."""
    config = Mock(spec=OrchestratorSettings)
    config.enable_optimizer_integration = True
    config.ml_local_load_prediction_enabled = True
    config.ml_allocation_outcomes_enabled = True
    config.ml_allocation_outcomes_topic = 'ml.allocation_outcomes'
    config.ml_optimization_timeout_seconds = 2
    config.mongodb_collection_tickets = 'execution_tickets'
    return config


@pytest.fixture
def mock_optimizer_client():
    """Cliente Optimizer gRPC mockado."""
    mock = AsyncMock()
    mock.get_load_forecast = AsyncMock(return_value={
        'forecast': [{'timestamp': 1234567890, 'value': 42.5}]
    })
    mock.get_scheduling_recommendation = AsyncMock(return_value={
        'action': 'SCALE_UP',
        'confidence': 0.85
    })
    return mock


@pytest.fixture
def mock_local_predictor():
    """LoadPredictor mockado."""
    mock = AsyncMock(spec=LoadPredictor)
    mock.predict_queue_time = AsyncMock(return_value=1500.0)
    mock.predict_worker_load = AsyncMock(return_value=0.4)
    mock.mongodb_client = Mock()  # Simular MongoDB disponível
    return mock


@pytest.fixture
def mock_kafka_producer():
    """Kafka producer mockado."""
    mock = AsyncMock()
    mock.send = AsyncMock(return_value={'published': True, 'offset': 123})
    return mock


@pytest.fixture
def mock_metrics():
    """Métricas mockadas."""
    return Mock(spec=OrchestratorMetrics)


@pytest.fixture
def scheduler_optimizer(
    mock_config,
    mock_optimizer_client,
    mock_local_predictor,
    mock_kafka_producer,
    mock_metrics
):
    """Instância de SchedulingOptimizer para testes."""
    return SchedulingOptimizer(
        config=mock_config,
        optimizer_client=mock_optimizer_client,
        local_predictor=mock_local_predictor,
        kafka_producer=mock_kafka_producer,
        metrics=mock_metrics
    )


class TestGetLoadForecast:
    """Testes de obtenção de load forecast."""

    @pytest.mark.asyncio
    async def test_get_load_forecast_from_remote(
        self,
        scheduler_optimizer,
        mock_optimizer_client,
        mock_metrics
    ):
        """Testa obtenção de forecast do optimizer remoto."""
        forecast = await scheduler_optimizer.get_load_forecast(horizon_minutes=60)

        assert forecast is not None
        assert 'forecast' in forecast
        mock_optimizer_client.get_load_forecast.assert_called_once()
        mock_metrics.update_optimizer_availability.assert_called_with(available=True)
        mock_metrics.record_ml_optimization.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_load_forecast_when_optimizer_disabled(
        self,
        mock_config,
        mock_local_predictor,
        mock_kafka_producer,
        mock_metrics
    ):
        """Testa forecast quando optimizer está desabilitado."""
        mock_config.enable_optimizer_integration = False
        optimizer = SchedulingOptimizer(
            config=mock_config,
            optimizer_client=None,
            local_predictor=mock_local_predictor,
            kafka_producer=mock_kafka_producer,
            metrics=mock_metrics
        )

        forecast = await optimizer.get_load_forecast()

        assert forecast is None

    @pytest.mark.asyncio
    async def test_get_load_forecast_when_optimizer_unavailable(
        self,
        scheduler_optimizer,
        mock_optimizer_client,
        mock_metrics
    ):
        """Testa forecast quando optimizer falha."""
        mock_optimizer_client.get_load_forecast.side_effect = Exception("Connection error")

        forecast = await scheduler_optimizer.get_load_forecast()

        assert forecast is None
        mock_metrics.update_optimizer_availability.assert_called_with(available=False)


class TestOptimizeAllocation:
    """Testes de otimização de alocação."""

    @pytest.mark.asyncio
    async def test_optimize_allocation_enriches_workers(
        self,
        scheduler_optimizer,
        mock_local_predictor
    ):
        """Testa enriquecimento de workers com predições ML."""
        ticket = {'ticket_id': 'ticket-1', 'task_type': 'deployment'}
        workers = [
            {'agent_id': 'worker-1', 'status': 'HEALTHY'},
            {'agent_id': 'worker-2', 'status': 'HEALTHY'}
        ]

        enriched = await scheduler_optimizer.optimize_allocation(
            ticket=ticket,
            workers=workers
        )

        assert len(enriched) == 2
        assert all('predicted_queue_ms' in w for w in enriched)
        assert all('predicted_load_pct' in w for w in enriched)
        assert all('ml_enriched' in w for w in enriched)
        assert all(w['ml_enriched'] is True for w in enriched)

    @pytest.mark.asyncio
    async def test_optimize_allocation_applies_rl_boost(
        self,
        scheduler_optimizer,
        mock_optimizer_client
    ):
        """Testa aplicação de RL boost quando recomendação tem confiança alta."""
        ticket = {'ticket_id': 'ticket-1'}
        workers = [
            {'agent_id': 'worker-1', 'predicted_load_pct': 0.2},  # Baixa carga
            {'agent_id': 'worker-2', 'predicted_load_pct': 0.8}   # Alta carga
        ]

        enriched = await scheduler_optimizer.optimize_allocation(
            ticket=ticket,
            workers=workers
        )

        # Ação SCALE_UP deve dar boost para workers com baixa carga
        assert enriched[0]['rl_boost'] == 1.2  # worker-1 tem boost
        assert enriched[1]['rl_boost'] == 1.0  # worker-2 sem boost

    @pytest.mark.asyncio
    async def test_optimize_allocation_no_rl_boost_low_confidence(
        self,
        scheduler_optimizer,
        mock_optimizer_client
    ):
        """Testa que boost não é aplicado quando confiança é baixa."""
        # Configurar confiança baixa
        mock_optimizer_client.get_scheduling_recommendation.return_value = {
            'action': 'SCALE_UP',
            'confidence': 0.5  # Abaixo do threshold de 0.6
        }

        ticket = {'ticket_id': 'ticket-1'}
        workers = [{'agent_id': 'worker-1', 'predicted_load_pct': 0.2}]

        enriched = await scheduler_optimizer.optimize_allocation(
            ticket=ticket,
            workers=workers
        )

        # Não deve ter boost se confiança é baixa
        assert enriched[0]['rl_boost'] == 1.0

    @pytest.mark.asyncio
    async def test_optimize_allocation_fallback_on_error(
        self,
        scheduler_optimizer,
        mock_local_predictor
    ):
        """Testa fallback quando otimização falha."""
        mock_local_predictor.predict_queue_time.side_effect = Exception("Prediction error")

        ticket = {'ticket_id': 'ticket-1'}
        workers = [{'agent_id': 'worker-1'}]

        # Deve retornar workers originais em caso de erro geral
        enriched = await scheduler_optimizer.optimize_allocation(
            ticket=ticket,
            workers=workers
        )

        # Fallback deve retornar workers originais
        assert enriched == workers


class TestRLRecommendationApplication:
    """Testes de aplicação de recomendações RL."""

    def test_apply_scale_up_recommendation(self, scheduler_optimizer):
        """Testa aplicação de recomendação SCALE_UP."""
        recommendation = {'action': 'SCALE_UP', 'confidence': 0.8}
        workers = [
            {'agent_id': 'w1', 'predicted_load_pct': 0.2},  # Baixa carga
            {'agent_id': 'w2', 'predicted_load_pct': 0.6},  # Alta carga
        ]

        result = scheduler_optimizer._apply_scheduling_recommendation(
            recommendation, workers
        )

        assert result[0]['rl_boost'] == 1.2  # Boost para baixa carga
        assert result[1]['rl_boost'] == 1.0  # Sem boost para alta carga

    def test_apply_consolidate_recommendation(self, scheduler_optimizer):
        """Testa aplicação de recomendação CONSOLIDATE."""
        recommendation = {'action': 'CONSOLIDATE', 'confidence': 0.75}
        workers = [
            {'agent_id': 'w1', 'predicted_load_pct': 0.3},  # Baixa carga
            {'agent_id': 'w2', 'predicted_load_pct': 0.7},  # Alta carga
        ]

        result = scheduler_optimizer._apply_scheduling_recommendation(
            recommendation, workers
        )

        assert result[0]['rl_boost'] == 1.0  # Sem boost para baixa carga
        assert result[1]['rl_boost'] == 1.1  # Boost para alta carga

    def test_apply_maintain_recommendation(self, scheduler_optimizer):
        """Testa aplicação de recomendação MAINTAIN."""
        recommendation = {'action': 'MAINTAIN', 'confidence': 0.9}
        workers = [
            {'agent_id': 'w1', 'predicted_load_pct': 0.5},
        ]

        result = scheduler_optimizer._apply_scheduling_recommendation(
            recommendation, workers
        )

        assert result[0]['rl_boost'] == 1.0  # Sem boost


class TestAllocationOutcomeRecording:
    """Testes de registro de allocation outcomes."""

    @pytest.mark.asyncio
    async def test_record_allocation_outcome_publishes_to_kafka(
        self,
        scheduler_optimizer,
        mock_kafka_producer,
        mock_metrics
    ):
        """Testa publicação de outcome no Kafka."""
        ticket = {
            'ticket_id': 'ticket-1',
            'status': 'COMPLETED',
            'risk_band': 'medium',
            'priority_score': 0.7
        }
        worker = {
            'agent_id': 'worker-1',
            'predicted_queue_ms': 1500.0,
            'predicted_load_pct': 0.4
        }

        await scheduler_optimizer.record_allocation_outcome(
            ticket=ticket,
            worker=worker,
            actual_duration_ms=1800.0
        )

        # Verificar chamada ao Kafka
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[1]['topic'] == 'ml.allocation_outcomes'
        assert 'ticket_id' in call_args[1]['value']

        # Verificar métricas
        mock_metrics.record_allocation_quality.assert_called_once()
        mock_metrics.record_queue_prediction_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_allocation_outcome_when_disabled(
        self,
        mock_config,
        mock_optimizer_client,
        mock_local_predictor,
        mock_kafka_producer,
        mock_metrics
    ):
        """Testa que outcome não é registrado quando desabilitado."""
        mock_config.ml_allocation_outcomes_enabled = False
        optimizer = SchedulingOptimizer(
            config=mock_config,
            optimizer_client=mock_optimizer_client,
            local_predictor=mock_local_predictor,
            kafka_producer=mock_kafka_producer,
            metrics=mock_metrics
        )

        ticket = {'ticket_id': 'ticket-1', 'status': 'COMPLETED'}
        worker = {'agent_id': 'worker-1'}

        await optimizer.record_allocation_outcome(
            ticket=ticket,
            worker=worker,
            actual_duration_ms=2000.0
        )

        # Não deve chamar Kafka
        mock_kafka_producer.send.assert_not_called()


class TestMetricsRecording:
    """Testes de registro de métricas."""

    @pytest.mark.asyncio
    async def test_records_optimization_metrics(
        self,
        scheduler_optimizer,
        mock_metrics
    ):
        """Testa registro de métricas de otimização."""
        ticket = {'ticket_id': 'ticket-1'}
        workers = [{'agent_id': 'w1'}]

        await scheduler_optimizer.optimize_allocation(ticket, workers)

        # Verificar registro de métricas de otimização
        mock_metrics.record_ml_optimization.assert_called()
