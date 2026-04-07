"""
Testes unitários para InsightsConsumer.

Cobre:
- Inicialização e configuração
- Loop de consumo de mensagens Kafka
- Processamento de insights
- Filtragem por prioridade
- Integração com OptimizationEngine e ExperimentManager
- Tratamento de erros
"""
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime

from src.consumers.insights_consumer import InsightsConsumer
from src.models.optimization_hypothesis import OptimizationHypothesis, OptimizationType
from src.models.optimization_event import OptimizationType as EventOptimizationType, Adjustment


@pytest.fixture
def mock_settings():
    """Settings mocados para testes."""
    settings = Mock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    settings.kafka_consumer_group_id = "optimizer-test-group"
    settings.kafka_insights_topic = "insights.generated"
    return settings


@pytest.fixture
def mock_optimization_engine():
    """Mock do OptimizationEngine."""
    engine = AsyncMock()
    engine.analyze_opportunity = AsyncMock(return_value=[])
    return engine


@pytest.fixture
def mock_experiment_manager():
    """Mock do ExperimentManager."""
    manager = AsyncMock()
    manager.submit_experiment = AsyncMock(return_value="exp-001")
    return manager


@pytest.fixture
def mock_metrics():
    """Mock de métricas."""
    metrics = Mock()
    metrics.increment_counter = Mock()
    metrics.record_hypothesis_generated = Mock()
    return metrics


@pytest.fixture
def sample_hypothesis():
    """Hipótese de exemplo para testes."""
    return OptimizationHypothesis(
        hypothesis_id="hyp-test-001",
        hypothesis_text="Reduce latency by adjusting weights",
        optimization_type=OptimizationType.WEIGHT_RECALIBRATION,
        target_component="consensus-engine",
        baseline_metrics={"latency_p95": 200.0, "error_rate": 0.01},
        target_metrics={"latency_p95": 150.0, "error_rate": 0.01},
        proposed_adjustments=[
            Adjustment(
                parameter="technical_weight",
                previous_value=0.25,
                new_value="0.30",
                justification="Improve accuracy",
            )
        ],
        expected_improvement=0.15,
        confidence_score=0.85,
        risk_score=0.3,
        priority=3,
        metadata={"context_id": "test-001"},
    )


@pytest.fixture
def insights_consumer(
    mock_settings, mock_optimization_engine, mock_experiment_manager, mock_metrics
):
    """Fixture do InsightsConsumer."""
    return InsightsConsumer(
        settings=mock_settings,
        optimization_engine=mock_optimization_engine,
        experiment_manager=mock_experiment_manager,
        metrics=mock_metrics,
    )


class TestInsightsConsumerInitialization:
    """Testes de inicialização do InsightsConsumer."""

    def test_initialization_with_all_dependencies(
        self, mock_settings, mock_optimization_engine, mock_experiment_manager, mock_metrics
    ):
        """Testa inicialização com todas as dependências."""
        consumer = InsightsConsumer(
            settings=mock_settings,
            optimization_engine=mock_optimization_engine,
            experiment_manager=mock_experiment_manager,
            metrics=mock_metrics,
        )

        assert consumer.settings == mock_settings
        assert consumer.optimization_engine == mock_optimization_engine
        assert consumer.experiment_manager == mock_experiment_manager
        assert consumer.metrics == mock_metrics
        assert consumer.consumer is None
        assert consumer.running is False

    def test_initialization_with_minimal_params(self, mock_settings):
        """Testa inicialização com parâmetros mínimos."""
        consumer = InsightsConsumer(settings=mock_settings)

        assert consumer.settings == mock_settings
        assert consumer.optimization_engine is None
        assert consumer.experiment_manager is None
        assert consumer.metrics is None

    def test_initialization_without_settings(self):
        """Testa inicialização sem settings (usa get_settings)."""
        with patch("src.consumers.insights_consumer.get_settings") as mock_get_settings:
            mock_settings = Mock()
            mock_settings.kafka_bootstrap_servers = "localhost:9092"
            mock_get_settings.return_value = mock_settings

            consumer = InsightsConsumer()

            assert consumer.settings == mock_settings
            mock_get_settings.assert_called_once()


class TestInsightsConsumerStart:
    """Testes de início do consumer."""

    def test_start_creates_kafka_consumer(self, insights_consumer):
        """Testa que start cria consumer Kafka."""
        with patch("src.consumers.insights_consumer.Consumer") as mock_consumer_class:
            mock_consumer = Mock()
            mock_consumer_class.return_value = mock_consumer

            with patch("asyncio.create_task"):
                insights_consumer.start()

                mock_consumer_class.assert_called_once()
                mock_consumer.subscribe.assert_called_once_with(
                    [insights_consumer.settings.kafka_insights_topic]
                )

    def test_start_sets_running_flag(self, insights_consumer):
        """Testa que start define flag running como True."""
        with patch("src.consumers.insights_consumer.Consumer"):
            with patch("asyncio.create_task"):
                insights_consumer.start()
                assert insights_consumer.running is True

    def test_start_creates_background_task(self, insights_consumer):
        """Testa que start cria tarefa em background."""
        with patch("src.consumers.insights_consumer.Consumer"):
            with patch("asyncio.create_task") as mock_create_task:
                mock_task = Mock()
                mock_create_task.return_value = mock_task

                insights_consumer.start()

                mock_create_task.assert_called_once()

    def test_start_handles_exception(self, insights_consumer):
        """Testa que start trata exceções adequadamente."""
        with patch(
            "src.consumers.insights_consumer.Consumer", side_effect=Exception("Kafka error")
        ):
            with pytest.raises(Exception) as exc_info:
                insights_consumer.start()

            assert "Kafka error" in str(exc_info.value)


class TestProcessMessage:
    """Testes de processamento de mensagens."""

    @pytest.mark.asyncio
    async def test_process_message_deserializes_json(self, insights_consumer):
        """Testa deserialização de JSON."""
        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        await insights_consumer._process_message(mock_msg)

        # Não deve gerar exceção

    @pytest.mark.asyncio
    async def test_process_message_handles_invalid_json(self, insights_consumer):
        """Testa tratamento de JSON inválido."""
        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = "invalid json{{{"

        # Não deve gerar exceção, apenas logar erro
        await insights_consumer._process_message(mock_msg)

    @pytest.mark.asyncio
    async def test_process_message_filters_low_priority(
        self, insights_consumer, mock_optimization_engine
    ):
        """Testa filtragem de insights de baixa prioridade."""
        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "MEDIUM",  # Deve ser filtrado
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        await insights_consumer._process_message(mock_msg)

        # analyze_opportunity não deve ser chamado para prioridade MEDIUM
        mock_optimization_engine.analyze_opportunity.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_accepts_high_priority(
        self, insights_consumer, mock_optimization_engine
    ):
        """Testa aceitação de insights de alta prioridade."""
        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",  # Deve ser aceito
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        await insights_consumer._process_message(mock_msg)

        # analyze_opportunity deve ser chamado
        mock_optimization_engine.analyze_opportunity.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_accepts_critical_priority(
        self, insights_consumer, mock_optimization_engine
    ):
        """Testa aceitação de insights de prioridade crítica."""
        insight_data = {
            "insight_id": "insight-002",
            "insight_type": "ANOMALY",
            "priority": "CRITICAL",  # Deve ser aceito
            "metrics": {"latency_p95": 500.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        await insights_consumer._process_message(mock_msg)

        # analyze_opportunity deve ser chamado
        mock_optimization_engine.analyze_opportunity.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_with_unknown_priority(
        self, insights_consumer, mock_optimization_engine
    ):
        """Testa comportamento com prioridade desconhecida."""
        insight_data = {
            "insight_id": "insight-003",
            "insight_type": "STRATEGIC",
            "priority": "UNKNOWN",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        await insights_consumer._process_message(mock_msg)

        # Deve ser filtrado (não é HIGH nem CRITICAL)
        mock_optimization_engine.analyze_opportunity.assert_not_called()


class TestHypothesisGeneration:
    """Testes de geração de hipóteses."""

    @pytest.mark.asyncio
    async def test_process_message_generates_hypotheses(
        self, insights_consumer, mock_optimization_engine, sample_hypothesis
    ):
        """Testa geração de hipóteses a partir de insight."""
        mock_optimization_engine.analyze_opportunity.return_value = [sample_hypothesis]

        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        await insights_consumer._process_message(mock_msg)

        # Verificar que analyze_opportunity foi chamado
        mock_optimization_engine.analyze_opportunity.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_submits_to_experiment_manager(
        self,
        insights_consumer,
        mock_optimization_engine,
        mock_experiment_manager,
        sample_hypothesis,
    ):
        """Testa submissão de hipótese para ExperimentManager."""
        mock_optimization_engine.analyze_opportunity.return_value = [sample_hypothesis]
        mock_experiment_manager.submit_experiment.return_value = "exp-123"

        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        await insights_consumer._process_message(mock_msg)

        # Verificar que submit_experiment foi chamado
        mock_experiment_manager.submit_experiment.assert_called_once_with(sample_hypothesis)

    @pytest.mark.asyncio
    async def test_process_message_handles_experiment_manager_none(
        self, insights_consumer, mock_optimization_engine, sample_hypothesis
    ):
        """Testa processamento sem ExperimentManager."""
        insights_consumer.experiment_manager = None
        mock_optimization_engine.analyze_opportunity.return_value = [sample_hypothesis]

        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        # Não deve gerar exceção
        await insights_consumer._process_message(mock_msg)

    @pytest.mark.asyncio
    async def test_process_message_handles_submit_experiment_none(
        self,
        insights_consumer,
        mock_optimization_engine,
        mock_experiment_manager,
        sample_hypothesis,
    ):
        """Testa quando submit_experiment retorna None."""
        mock_optimization_engine.analyze_opportunity.return_value = [sample_hypothesis]
        mock_experiment_manager.submit_experiment.return_value = None

        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        # Não deve gerar exceção
        await insights_consumer._process_message(mock_msg)

    @pytest.mark.asyncio
    async def test_process_message_handles_submit_experiment_exception(
        self,
        insights_consumer,
        mock_optimization_engine,
        mock_experiment_manager,
        sample_hypothesis,
    ):
        """Testa tratamento de exceção ao submeter experimento."""
        mock_optimization_engine.analyze_opportunity.return_value = [sample_hypothesis]
        mock_experiment_manager.submit_experiment.side_effect = Exception("Submission failed")

        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        # Não deve gerar exceção
        await insights_consumer._process_message(mock_msg)

    @pytest.mark.asyncio
    async def test_process_message_handles_optimization_engine_none(self, insights_consumer):
        """Testa processamento sem OptimizationEngine."""
        insights_consumer.optimization_engine = None

        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        # Não deve gerar exceção
        await insights_consumer._process_message(mock_msg)


class TestMetrics:
    """Testes de métricas."""

    @pytest.mark.asyncio
    async def test_process_message_records_hypothesis_generated(
        self, insights_consumer, mock_optimization_engine, mock_metrics, sample_hypothesis
    ):
        """Testa registro de hipótese gerada nas métricas."""
        mock_optimization_engine.analyze_opportunity.return_value = [sample_hypothesis]

        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        await insights_consumer._process_message(mock_msg)

        # Verificar que record_hypothesis_generated foi chamado
        mock_metrics.record_hypothesis_generated.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_handles_metrics_none(
        self, insights_consumer, mock_optimization_engine, sample_hypothesis
    ):
        """Testa processamento sem métricas."""
        insights_consumer.metrics = None
        mock_optimization_engine.analyze_opportunity.return_value = [sample_hypothesis]

        insight_data = {
            "insight_id": "insight-001",
            "insight_type": "OPERATIONAL",
            "priority": "HIGH",
            "metrics": {"latency_p95": 200.0},
        }

        mock_msg = Mock()
        mock_msg.value = Mock()
        mock_msg.value.decode.return_value = json.dumps(insight_data)

        # Não deve gerar exceção
        await insights_consumer._process_message(mock_msg)


class TestStop:
    """Testes de parada do consumer."""

    def test_stop_sets_running_flag_false(self, insights_consumer):
        """Testa que stop define running como False."""
        insights_consumer.running = True

        mock_consumer = Mock()
        insights_consumer.consumer = mock_consumer

        insights_consumer.stop()

        assert insights_consumer.running is False
        mock_consumer.close.assert_called_once()

    def test_stop_without_consumer(self, insights_consumer):
        """Testa stop sem consumer inicializado."""
        insights_consumer.consumer = None
        insights_consumer.running = True

        # Não deve gerar exceção
        insights_consumer.stop()

        assert insights_consumer.running is False
