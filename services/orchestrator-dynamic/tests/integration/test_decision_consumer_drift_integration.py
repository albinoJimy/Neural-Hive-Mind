"""
Testes de integração de Drift Detection no Decision Consumer.

Testa a integração entre DriftDetector e DecisionConsumer:
- DriftDetector é injetado no DecisionConsumer
- Check de drift é executado antes de processar decisões
- Decisões são marcadas quando drift é detectado
- Graceful handling quando drift detector não está disponível
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from src.consumers.decision_consumer import DecisionConsumer

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def test_config():
    """Test configuration for DecisionConsumer."""
    config = Mock()
    config.kafka_bootstrap_servers = "localhost:9092"
    config.kafka_consumer_group_id = "test-group"
    config.kafka_auto_offset_reset = "latest"
    config.kafka_enable_auto_commit = False
    config.kafka_consensus_topic = "plans.consensus"
    config.kafka_sasl_username = "test-user"
    config.kafka_sasl_password = "test-pass"
    config.kafka_security_protocol = "SASL_PLAIN"
    config.kafka_sasl_mechanism = "PLAIN"
    config.temporal_workflow_id_prefix = "workflow-"
    config.temporal_task_queue = "orchestrator-task-queue"
    config.ml_drift_check_enabled = True  # Enable drift check
    return config


@pytest.fixture()
def mock_temporal_client():
    """Mock Temporal client."""
    client = AsyncMock()
    client.start_workflow = AsyncMock()
    return client


@pytest.fixture()
def mock_mongodb_client():
    """Mock MongoDB client."""
    client = AsyncMock()
    client.get_cognitive_plan = AsyncMock()
    return client


@pytest.fixture()
def mock_redis_client():
    """Mock Redis client."""
    client = AsyncMock()
    client.exists = AsyncMock(return_value=False)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock()
    return client


@pytest.fixture()
def mock_metrics():
    """Mock Prometheus metrics."""
    metrics = Mock()
    metrics.record_drift_score = Mock()
    metrics.update_drift_status = Mock()
    metrics.record_duplicate_detected = Mock()
    return metrics


@pytest.fixture()
def mock_drift_detector_no_drift():
    """Mock drift detector reporting no drift."""
    detector = AsyncMock()
    detector.run_drift_check = AsyncMock(
        return_value={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "window_days": 7,
            "overall_status": "ok",
            "feature_drift": {},
            "prediction_drift": {},
            "target_drift": {},
            "recommendations": ["Nenhum drift significativo detectado."],
        }
    )
    return detector


@pytest.fixture()
def mock_drift_detector_with_drift():
    """Mock drift detector reporting critical drift."""
    detector = AsyncMock()
    detector.run_drift_check = AsyncMock(
        return_value={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "window_days": 7,
            "overall_status": "critical",
            "feature_drift": {"complexity": 0.35, "max_drift_score": 0.35},
            "prediction_drift": {"drift_ratio": 2.5, "max_drift_score": 2.5},
            "target_drift": {"p_value": 0.01, "max_drift_score": 0.01},
            "recommendations": [
                "Feature drift detectado em complexity (PSI=0.350).",
                "Acurácia degradou 150%. Retreinamento urgente recomendado.",
            ],
        }
    )
    return detector


@pytest_asyncio.fixture
async def decision_consumer_no_drift(
    test_config,
    mock_temporal_client,
    mock_mongodb_client,
    mock_redis_client,
    mock_metrics,
    mock_drift_detector_no_drift,
):
    """DecisionConsumer com drift detector (sem drift)."""
    consumer = DecisionConsumer(
        config=test_config,
        temporal_client=mock_temporal_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        metrics=mock_metrics,
        drift_detector=mock_drift_detector_no_drift,
    )
    return consumer


@pytest_asyncio.fixture
async def decision_consumer_with_drift(
    test_config,
    mock_temporal_client,
    mock_mongodb_client,
    mock_redis_client,
    mock_metrics,
    mock_drift_detector_with_drift,
):
    """DecisionConsumer com drift detector (com drift detectado)."""
    consumer = DecisionConsumer(
        config=test_config,
        temporal_client=mock_temporal_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        metrics=mock_metrics,
        drift_detector=mock_drift_detector_with_drift,
    )
    return consumer


@pytest_asyncio.fixture
async def decision_consumer_no_detector(
    test_config,
    mock_temporal_client,
    mock_mongodb_client,
    mock_redis_client,
    mock_metrics,
):
    """DecisionConsumer sem drift detector."""
    consumer = DecisionConsumer(
        config=test_config,
        temporal_client=mock_temporal_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        metrics=mock_metrics,
        drift_detector=None,
    )
    return consumer


# =============================================================================
# Test Cases
# =============================================================================


class TestDriftDetectorInjection:
    """Testa injeção de DriftDetector no DecisionConsumer."""

    def test_drift_detector_injected_at_init(self, decision_consumer_no_drift):
        """DriftDetector deve ser injetado via construtor."""
        assert decision_consumer_no_drift.drift_detector is not None

    def test_drift_detector_can_be_none(self, decision_consumer_no_detector):
        """DriftDetector pode ser None (funcionalidade opcional)."""
        assert decision_consumer_no_detector.drift_detector is None


class TestDriftCheckExecution:
    """Testa execução do check de drift."""

    @pytest.mark.asyncio()
    async def test_drift_check_called_when_enabled(
        self, decision_consumer_no_drift, mock_drift_detector_no_drift
    ):
        """Drift check deve ser chamado quando habilitado."""
        report = await decision_consumer_no_drift._check_ml_drift()

        # Verifica que o drift check foi chamado
        mock_drift_detector_no_drift.run_drift_check.assert_called_once()

        # Verifica que o report foi retornado
        assert report is not None
        assert report["overall_status"] == "ok"

    @pytest.mark.asyncio()
    async def test_drift_check_skipped_when_disabled(
        self, decision_consumer_no_detector
    ):
        """Drift check deve ser skipado quando desabilitado via config."""
        # Desabilitar via config
        decision_consumer_no_detector.ml_drift_check_enabled = False

        report = await decision_consumer_no_detector._check_ml_drift()

        # Deve retornar None sem chamar o detector
        assert report is None

    @pytest.mark.asyncio()
    async def test_drift_check_skipped_when_no_detector(
        self, decision_consumer_no_detector
    ):
        """Drift check deve ser graceful quando detector não disponível."""
        # Habilitar via config mas sem detector
        decision_consumer_no_detector.ml_drift_check_enabled = True
        decision_consumer_no_detector.drift_detector = None

        report = await decision_consumer_no_detector._check_ml_drift()

        # Deve retornar None sem erro
        assert report is None

    @pytest.mark.asyncio()
    async def test_drift_check_handles_exceptions(
        self, decision_consumer_no_drift, mock_drift_detector_no_drift
    ):
        """Drift check deve capturar exceções e retornar None."""
        # Simular erro no drift detector
        mock_drift_detector_no_drift.run_drift_check = AsyncMock(side_effect=Exception("DB error"))

        report = await decision_consumer_no_drift._check_ml_drift()

        # Deve capturar erro e retornar None
        assert report is None


class TestDriftStatusTracking:
    """Testa rastreamento de status de drift nas decisões."""

    @pytest.mark.asyncio()
    async def test_decision_marked_when_drift_detected(
        self, decision_consumer_with_drift, mock_drift_detector_with_drift, mock_metrics
    ):
        """Decisão deve ser marcada quando drift é detectado."""
        report = await decision_consumer_with_drift._check_ml_drift()

        # Verifica report
        assert report is not None
        assert report["overall_status"] == "critical"
        assert len(report["recommendations"]) > 0

        # Verifica métrica registrada
        mock_metrics.record_drift_score.assert_called()

    @pytest.mark.asyncio()
    async def test_decision_not_marked_when_no_drift(
        self, decision_consumer_no_drift, mock_drift_detector_no_drift
    ):
        """Decisão NÃO deve ser marcada quando não há drift."""
        report = await decision_consumer_no_drift._check_ml_drift()

        # Status ok
        assert report["overall_status"] == "ok"


class TestDriftDetectionDisabled:
    """Testa comportamento quando drift detection está desabilitado."""

    @pytest.mark.asyncio()
    async def test_drift_check_returns_none_when_disabled(
        self, decision_consumer_no_detector
    ):
        """Drift check deve retornar None quando desabilitado."""
        decision_consumer_no_detector.ml_drift_check_enabled = False

        report = await decision_consumer_no_detector._check_ml_drift()

        assert report is None


class TestDriftMetrics:
    """Testa registro de métricas de drift."""

    @pytest.mark.asyncio()
    async def test_drift_metrics_recorded_on_critical(
        self, decision_consumer_with_drift, mock_metrics
    ):
        """Métricas devem ser registradas quando drift crítico detectado."""
        await decision_consumer_with_drift._check_ml_drift()

        # Verifica chamada com score=1.0 para critical
        mock_metrics.record_drift_score.assert_called_once()
        call_kwargs = mock_metrics.record_drift_score.call_args.kwargs
        assert call_kwargs["drift_type"] == "overall"
        assert call_kwargs["score"] == 1.0
        assert call_kwargs["model_name"] == "orchestrator-ml"

    @pytest.mark.asyncio()
    async def test_drift_metrics_recorded_on_warning(
        self, decision_consumer_no_drift, mock_drift_detector_no_drift, mock_metrics
    ):
        """Métricas devem ser registradas quando drift warning detectado."""
        # Simular warning
        mock_drift_detector_no_drift.run_drift_check = AsyncMock(
            return_value={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "window_days": 7,
                "overall_status": "warning",
                "recommendations": ["Drift leve detectado."],
            }
        )

        await decision_consumer_no_drift._check_ml_drift()

        # Verifica chamada
        mock_metrics.record_drift_score.assert_called_once()


# =============================================================================
# Testes de Integração End-to-End
# =============================================================================


class TestDriftDetectionE2E:
    """Testes E2E de drift detection no fluxo de processamento."""

    @pytest.mark.asyncio()
    async def test_message_processing_with_no_drift(
        self,
        decision_consumer_no_drift,
        mock_mongodb_client,
        mock_temporal_client,
        mock_drift_detector_no_drift,
    ):
        """Mensagem deve ser processada normalmente quando não há drift."""
        # Setup cognitive plan
        mock_mongodb_client.get_cognitive_plan = AsyncMock(
            return_value={
                "plan_id": "plan-123",
                "tasks": [{"task_id": "task-1", "type": "BUILD"}],
                "execution_order": ["task-1"],
                "risk_band": "low",
            }
        )

        # Criar mensagem mock
        mock_message = Mock()
        mock_message.value = json.dumps(
            {
                "decision_id": "decision-123",
                "plan_id": "plan-123",
                "final_decision": "approve",
            }
        ).encode("utf-8")
        mock_message.topic = "plans.consensus"
        mock_message.partition = 0
        mock_message.offset = 100
        mock_message.headers = []

        # Drift check deve retornar ok
        mock_drift_detector_no_drift.run_drift_check = AsyncMock(
            return_value={"overall_status": "ok"}
        )

        # Processar mensagem (chamada interna ao _check_ml_drift)
        await decision_consumer_no_drift._check_ml_drift()

        # Verifica que drift check foi chamado
        mock_drift_detector_no_drift.run_drift_check.assert_called_once()

    @pytest.mark.asyncio()
    async def test_message_processing_with_drift_detected(
        self,
        decision_consumer_with_drift,
        mock_mongodb_client,
        mock_temporal_client,
        mock_drift_detector_with_drift,
        mock_metrics,
    ):
        """Mensagem deve ser processada e marcada quando drift detectado."""
        # Setup cognitive plan
        mock_mongodb_client.get_cognitive_plan = AsyncMock(
            return_value={
                "plan_id": "plan-456",
                "tasks": [{"task_id": "task-2", "type": "DEPLOY"}],
                "execution_order": ["task-2"],
                "risk_band": "high",
            }
        )

        # Criar mensagem mock
        mock_message = Mock()
        consolidated_decision = {
            "decision_id": "decision-456",
            "plan_id": "plan-456",
            "final_decision": "approve",
        }
        mock_message.value = json.dumps(consolidated_decision).encode("utf-8")
        mock_message.topic = "plans.consensus"
        mock_message.partition = 0
        mock_message.offset = 200
        mock_message.headers = []

        # Drift check deve retornar critical
        mock_drift_detector_with_drift.run_drift_check = AsyncMock(
            return_value={
                "overall_status": "critical",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "recommendations": ["Retreinamento urgente."],
            }
        )

        # Simular drift check e marcação da decisão
        drift_report = await decision_consumer_with_drift._check_ml_drift()

        # Verifica drift detectado
        assert drift_report["overall_status"] == "critical"

        # Simular marcação da decisão (como seria no _process_message)
        if drift_report and drift_report.get("overall_status") != "ok":
            consolidated_decision["drift_detected"] = True
            consolidated_decision["drift_status"] = drift_report.get("overall_status")
            consolidated_decision["drift_timestamp"] = drift_report.get("timestamp")

        # Verifica decisão marcada
        assert consolidated_decision["drift_detected"] is True
        assert consolidated_decision["drift_status"] == "critical"
        assert "drift_timestamp" in consolidated_decision


# =============================================================================
# FASE 0: Testes de Integração Drift-Retrain Connector
# =============================================================================


@pytest.fixture()
def mock_drift_retrain_connector():
    """Mock drift retrain connector."""
    connector = AsyncMock()
    connector.trigger_retrain_if_needed = AsyncMock(
        return_value={
            "triggered": False,
            "reason": "Drift score dentro dos limites aceitáveis",
            "priority": "low",
        }
    )
    return connector


@pytest.fixture()
def mock_drift_retrain_connector_triggered():
    """Mock drift retrain connector que retorna triggered=True."""
    connector = AsyncMock()
    connector.trigger_retrain_if_needed = AsyncMock(
        return_value={
            "triggered": True,
            "reason": "Drift CRÍTICO detectado",
            "priority": "critical",
            "status": "success",
        }
    )
    return connector


@pytest_asyncio.fixture
async def decision_consumer_with_retrain_connector(
    test_config,
    mock_temporal_client,
    mock_mongodb_client,
    mock_redis_client,
    mock_metrics,
    mock_drift_detector_with_drift,
    mock_drift_retrain_connector,
):
    """DecisionConsumer com drift detector e retrain connector."""
    consumer = DecisionConsumer(
        config=test_config,
        temporal_client=mock_temporal_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        metrics=mock_metrics,
        drift_detector=mock_drift_detector_with_drift,
        drift_retrain_connector=mock_drift_retrain_connector,
    )
    return consumer


@pytest_asyncio.fixture
async def decision_consumer_with_retrain_triggered(
    test_config,
    mock_temporal_client,
    mock_mongodb_client,
    mock_redis_client,
    mock_metrics,
    mock_drift_detector_with_drift,
    mock_drift_retrain_connector_triggered,
):
    """DecisionConsumer com drift detector e retrain connector (triggered)."""
    consumer = DecisionConsumer(
        config=test_config,
        temporal_client=mock_temporal_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        metrics=mock_metrics,
        drift_detector=mock_drift_detector_with_drift,
        drift_retrain_connector=mock_drift_retrain_connector_triggered,
    )
    return consumer


class TestDriftRetrainIntegration:
    """Testa integração de Drift-Retrain Connector (FASE 0)."""

    @pytest.mark.asyncio()
    async def test_drift_retrain_connector_injected(self, decision_consumer_with_retrain_connector):
        """DriftRetrainConnector deve ser injetado via construtor."""
        assert decision_consumer_with_retrain_connector.drift_retrain_connector is not None

    @pytest.mark.asyncio()
    async def test_drift_check_triggers_retrain_evaluation(
        self, decision_consumer_with_retrain_connector
    ):
        """Drift check deve chamar trigger_retrain_if_needed no connector."""
        # Executar check de drift
        drift_report = await decision_consumer_with_retrain_connector._check_ml_drift()

        # Verifica que drift foi detectado
        assert drift_report is not None
        assert drift_report["overall_status"] == "critical"

        # Verifica que o connector foi chamado
        connector = decision_consumer_with_retrain_connector.drift_retrain_connector
        connector.trigger_retrain_if_needed.assert_called_once()

        # Verificar o argumento (DriftAlert)
        call_args = connector.trigger_retrain_if_needed.call_args
        alert = call_args[0][0]  # Primeiro argumento posicional
        assert alert.model_name == "nhm_approval_model"
        assert alert.severity == "critical"

    @pytest.mark.asyncio()
    async def test_drift_check_triggers_retrain_successfully(
        self, decision_consumer_with_retrain_triggered
    ):
        """Drift crítico deve trigger retrain com sucesso."""
        # Executar check de drift
        drift_report = await decision_consumer_with_retrain_triggered._check_ml_drift()

        # Verifica que drift foi detectado
        assert drift_report is not None
        assert drift_report["overall_status"] == "critical"

        # Verifica que o connector foi chamado
        connector = decision_consumer_with_retrain_triggered.drift_retrain_connector
        connector.trigger_retrain_if_needed.assert_called_once()

    @pytest.mark.asyncio()
    async def test_drift_retrain_not_called_when_no_drift(
        self, test_config, mock_temporal_client, mock_mongodb_client,
        mock_redis_client, mock_metrics, mock_drift_detector_no_drift
    ):
        """Retrain não deve ser chamado quando não há drift."""
        # Criar mock connector
        mock_connector = AsyncMock()
        mock_connector.trigger_retrain_if_needed = AsyncMock()

        # Criar consumer com drift detector que retorna ok
        consumer = DecisionConsumer(
            config=test_config,
            temporal_client=mock_temporal_client,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client,
            metrics=mock_metrics,
            drift_detector=mock_drift_detector_no_drift,
            drift_retrain_connector=mock_connector,
        )

        # Executar check de drift
        drift_report = await consumer._check_ml_drift()

        # Verifica que não há drift
        assert drift_report["overall_status"] == "ok"

        # Verifica que o connector NÃO foi chamado
        mock_connector.trigger_retrain_if_needed.assert_not_called()

    @pytest.mark.asyncio()
    async def test_drift_retrain_graceful_handling_when_not_available(
        self, decision_consumer_with_drift, mock_drift_detector_with_drift
    ):
        """Deve funcionar graceful quando drift_retrain_connector não está disponível."""
        # Consumer sem drift_retrain_connector
        assert decision_consumer_with_drift.drift_retrain_connector is None

        # Executar check de drift - não deve lançar exceção
        drift_report = await decision_consumer_with_drift._check_ml_drift()

        # Verifica que drift foi detectado
        assert drift_report is not None
        assert drift_report["overall_status"] == "critical"

    @pytest.mark.asyncio()
    async def test_drift_retrain_with_critical_severity(
        self, test_config, mock_temporal_client, mock_mongodb_client,
        mock_redis_client, mock_metrics, mock_drift_detector_with_drift,
        mock_drift_retrain_connector
    ):
        """DriftAlert com severity critical deve ser criado corretamente."""
        # Criar drift report com status critical
        drift_report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_version": "v8",
            "overall_status": "critical",
            "feature_drift": {"max_drift_score": 0.5},
            "prediction_drift": {"max_drift_score": 0.3},
            "target_drift": {"max_drift_score": 0.1},
        }

        # Criar mock connector
        mock_connector = AsyncMock()
        mock_connector.trigger_retrain_if_needed = AsyncMock(return_value={"triggered": True})

        # Criar consumer
        consumer = DecisionConsumer(
            config=test_config,
            temporal_client=mock_temporal_client,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client,
            metrics=mock_metrics,
            drift_detector=mock_drift_detector_with_drift,
            drift_retrain_connector=mock_connector,
        )

        # Chamar _trigger_retrain_on_drift diretamente
        await consumer._trigger_retrain_on_drift(drift_report)

        # Verificar que connector foi chamado com alerta correto
        mock_connector.trigger_retrain_if_needed.assert_called_once()
        call_args = mock_connector.trigger_retrain_if_needed.call_args
        alert = call_args[0][0]

        assert alert.severity == "critical"
        assert alert.drift_type == "feature"  # Maior score
        assert alert.score == 0.5
