"""Testes unitários para DriftDetector - Detecção de Model Drift."""

import pytest
import numpy as np
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call

from neural_hive_ml.drift_detector import DriftDetector, CanaryDeployer


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_mongo_client():
    """Mock do cliente MongoDB."""
    client = Mock()
    db = Mock()
    client.__getitem__ = Mock(return_value=db)
    client.plan_approvals = Mock()
    client.model_versions = Mock()
    return client


@pytest.fixture
def mock_kafka_producer():
    """Mock do producer Kafka."""
    producer = AsyncMock()
    producer.produce_and_wait = AsyncMock(return_value=True)
    return producer


@pytest.fixture
def drift_detector(mock_mongo_client, mock_kafka_producer):
    """Fixture para DriftDetector."""
    return DriftDetector(
        mongo_client=mock_mongo_client,
        kafka_producer=mock_kafka_producer,
        confidence_threshold=0.10,
        approve_rate_threshold=0.15,
        baseline_window_hours=168,
    )


@pytest.fixture
def mock_aggregation_results():
    """Mock de resultados de agregação MongoDB."""
    return {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}


# =============================================================================
# Testes: DriftDetector - Inicialização
# =============================================================================


class TestDriftDetectorInitialization:
    """Testes para inicialização do DriftDetector."""

    def test_drift_detector_initialization_with_defaults(self, mock_mongo_client):
        """Testa inicialização com valores padrão."""
        detector = DriftDetector(mongo_client=mock_mongo_client, kafka_producer=None)

        assert detector.mongo_client == mock_mongo_client
        assert detector.kafka_producer is None
        assert detector.confidence_threshold == 0.10
        assert detector.approve_rate_threshold == 0.15
        assert detector.baseline_window_hours == 168

    def test_drift_detector_initialization_with_custom_thresholds(
        self, mock_mongo_client, mock_kafka_producer
    ):
        """Testa inicialização com thresholds personalizados."""
        detector = DriftDetector(
            mongo_client=mock_mongo_client,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.15,
            approve_rate_threshold=0.20,
            baseline_window_hours=72,
        )

        assert detector.confidence_threshold == 0.15
        assert detector.approve_rate_threshold == 0.20
        assert detector.baseline_window_hours == 72

    def test_db_property_returns_mongo_client(self, drift_detector):
        """Testa que property db retorna mongo_client."""
        assert drift_detector.db == drift_detector.mongo_client


# =============================================================================
# Testes: DriftDetector - Build Aggregation Pipeline
# =============================================================================


class TestBuildAggregationPipeline:
    """Testes para _build_aggregation_pipeline."""

    def test_build_aggregation_pipeline_structure(self, drift_detector):
        """Testa estrutura do pipeline de agregação."""
        window_hours = 24
        pipeline = drift_detector._build_aggregation_pipeline(window_hours)

        assert isinstance(pipeline, list)
        assert len(pipeline) == 2

        # Primeiro estágio: $match
        match_stage = pipeline[0]
        assert "$match" in match_stage
        assert "created_at" in match_stage["$match"]
        assert "$gte" in match_stage["$match"]["created_at"]

        # Segundo estágio: $group
        group_stage = pipeline[1]
        assert "$group" in group_stage
        assert "_id" in group_stage["$group"]
        assert "approve_rate" in group_stage["$group"]
        assert "avg_confidence" in group_stage["$group"]
        assert "count" in group_stage["$group"]

    def test_build_aggregation_pipeline_timestamp_calculation(self, drift_detector):
        """Testa cálculo de timestamp no pipeline."""
        window_hours = 24
        pipeline = drift_detector._build_aggregation_pipeline(window_hours)

        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        match_since = pipeline[0]["$match"]["created_at"]["$gte"]

        # Verifica que o timestamp está próximo (diferença de segundos aceitável)
        time_diff = abs((since - match_since).total_seconds())
        assert time_diff < 5  # Menos de 5 segundos de diferença


# =============================================================================
# Testes: DriftDetector - Calculate Baseline
# =============================================================================


class TestCalculateBaseline:
    """Testes para calculate_baseline."""

    @pytest.mark.asyncio
    async def test_calculate_baseline_with_results(self, drift_detector, mock_aggregation_results):
        """Testa cálculo de baseline com dados válidos."""
        # Mock da agregação
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[mock_aggregation_results])
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        result = await drift_detector.calculate_baseline(window_hours=168)

        assert result["approve_rate"] == 0.70
        assert result["avg_confidence"] == 0.75
        assert result["sample_count"] == 100

    @pytest.mark.asyncio
    async def test_calculate_baseline_with_empty_results(self, drift_detector):
        """Testa cálculo de baseline sem dados (retorna padrão)."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        result = await drift_detector.calculate_baseline(window_hours=168)

        # Valores padrão
        assert result["approve_rate"] == 0.65
        assert result["avg_confidence"] == 0.72
        assert result["sample_count"] == 0

    @pytest.mark.asyncio
    async def test_calculate_baseline_with_partial_results(self, drift_detector):
        """Testa cálculo de baseline com resultados parciais."""
        partial_result = {"_id": None, "count": 50}
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[partial_result])
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        result = await drift_detector.calculate_baseline(window_hours=168)

        assert result["approve_rate"] == 0.0
        assert result["avg_confidence"] == 0.0
        assert result["sample_count"] == 50

    @pytest.mark.asyncio
    async def test_calculate_baseline_on_error(self, drift_detector):
        """Testa tratamento de erro no cálculo de baseline."""
        drift_detector.db.plan_approvals.aggregate = Mock(side_effect=Exception("DB Error"))

        with pytest.raises(Exception, match="DB Error"):
            await drift_detector.calculate_baseline()


# =============================================================================
# Testes: DriftDetector - Calculate Current
# =============================================================================


class TestCalculateCurrent:
    """Testes para calculate_current."""

    @pytest.mark.asyncio
    async def test_calculate_current_with_results(self, drift_detector, mock_aggregation_results):
        """Testa cálculo de métricas atuais com dados válidos."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[mock_aggregation_results])
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        result = await drift_detector.calculate_current(window_hours=24)

        assert result["approve_rate"] == 0.70
        assert result["avg_confidence"] == 0.75
        assert result["sample_count"] == 100

    @pytest.mark.asyncio
    async def test_calculate_current_with_empty_results(self, drift_detector):
        """Testa cálculo de métricas atuais sem dados."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        result = await drift_detector.calculate_current(window_hours=24)

        assert result["approve_rate"] == 0.0
        assert result["avg_confidence"] == 0.0
        assert result["sample_count"] == 0


# =============================================================================
# Testes: DriftDetector - Get Active Model Version
# =============================================================================


class TestGetActiveModelVersion:
    """Testes para _get_active_model_version."""

    @pytest.mark.asyncio
    async def test_get_active_model_version_found(self, drift_detector):
        """Testa busca de versão ativa quando encontrado."""
        mock_doc = {
            "version": "v1.2.3",
            "stage": "production",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        }
        drift_detector.db.model_versions.find_one = AsyncMock(return_value=mock_doc)

        version = await drift_detector._get_active_model_version()

        assert version == "v1.2.3"

    @pytest.mark.asyncio
    async def test_get_active_model_version_not_found(self, drift_detector):
        """Testa busca de versão ativa quando não encontrado."""
        drift_detector.db.model_versions.find_one = AsyncMock(return_value=None)

        version = await drift_detector._get_active_model_version()

        assert version == "unknown"

    @pytest.mark.asyncio
    async def test_get_active_model_version_on_error(self, drift_detector):
        """Testa tratamento de erro na busca de versão."""
        drift_detector.db.model_versions.find_one = Mock(side_effect=Exception("Connection error"))

        version = await drift_detector._get_active_model_version()

        assert version == "unknown"


# =============================================================================
# Testes: DriftDetector - Detect Drift (sem drift)
# =============================================================================


class TestDetectDriftNoDrift:
    """Testes para detect_drift quando não há drift."""

    @pytest.mark.asyncio
    async def test_detect_drift_no_drift_similar_metrics(self, drift_detector):
        """Testa detecção quando métricas são semelhantes (sem drift)."""
        # Track call count to differentiate baseline vs current calls
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            # First call is baseline (168h), second is current (24h)
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.72,  # Diferença de 0.02 (< 0.15 threshold)
                            "avg_confidence": 0.76,  # Diferença de 0.01 (< 0.10 threshold)
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is False
        assert len(result["alerts"]) == 0
        assert result["baseline"]["approve_rate"] == 0.70
        assert result["current"]["approve_rate"] == 0.72

    @pytest.mark.asyncio
    async def test_detect_drift_exactly_at_threshold(self, drift_detector):
        """Testa detecção quando mudança é exatamente no threshold."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.70, "count": 100}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.70,  # Diferença de 0.00
                            "avg_confidence": 0.80,  # Diferença de 0.10 (exatamente threshold)
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift()

        # Com >= threshold deve detectar drift
        assert result["drift_detected"] is True
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["metric"] == "avg_confidence"


# =============================================================================
# Testes: DriftDetector - Detect Drift (mudança de média)
# =============================================================================


class TestDetectDriftMeanShift:
    """Testes para detect_drift com mudança de média."""

    @pytest.mark.asyncio
    async def test_detect_drift_mean_confidence_drop(self, drift_detector):
        """Testa detecção de queda na confiança média."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 100}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.70,
                            "avg_confidence": 0.68,  # Queda de 0.12 (> 0.10 threshold, < 0.15 critical)
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is True
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["metric"] == "avg_confidence"
        assert result["alerts"][0]["change"] == -0.12
        assert result["alerts"][0]["threshold"] == 0.10
        assert result["alerts"][0]["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_detect_drift_mean_confidence_increase(self, drift_detector):
        """Testa detecção de aumento na confiança média."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.60, "count": 100}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.70,
                            "avg_confidence": 0.75,  # Aumento de 0.15 (> 0.10 threshold)
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is True
        assert result["alerts"][0]["metric"] == "avg_confidence"
        assert result["alerts"][0]["change"] == 0.15

    @pytest.mark.asyncio
    async def test_detect_drift_approve_rate_change(self, drift_detector):
        """Testa detecção de mudança no approve rate."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.50,  # Queda de 0.20 (> 0.15 threshold)
                            "avg_confidence": 0.75,
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is True
        assert result["alerts"][0]["metric"] == "approve_rate"
        assert result["alerts"][0]["change"] == -0.20

    @pytest.mark.asyncio
    async def test_detect_drift_critical_severity(self, drift_detector):
        """Testa detecção de drift com severidade crítica."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 100}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.70,
                            "avg_confidence": 0.50,  # Queda de 0.30 (> 1.5 * 0.10)
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is True
        assert result["alerts"][0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_detect_drift_multiple_alerts(self, drift_detector):
        """Testa detecção de múltiplos drifts simultâneos."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 100}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.50,  # Queda de 0.20
                            "avg_confidence": 0.60,  # Queda de 0.20
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is True
        assert len(result["alerts"]) == 2
        metrics_alerted = [a["metric"] for a in result["alerts"]]
        assert "approve_rate" in metrics_alerted
        assert "avg_confidence" in metrics_alerted


# =============================================================================
# Testes: DriftDetector - Detect Drift (com timestamps)
# =============================================================================


class TestDetectDriftWithTimestamps:
    """Testes para rastreamento de drift ao longo do tempo."""

    @pytest.mark.asyncio
    async def test_detect_drift_includes_timestamp(self, drift_detector):
        """Testa que resultado inclui timestamp de última atualização."""

        def mock_aggregate(window_hours):
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(
                return_value=[
                    {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                ]
            )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift()

        assert "last_updated" in result
        # Verifica formato ISO
        datetime.fromisoformat(result["last_updated"])

    @pytest.mark.asyncio
    async def test_detect_drift_window_hours_in_result(self, drift_detector):
        """Testa que window_hours está incluído no resultado."""

        def mock_aggregate(window_hours):
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(
                return_value=[
                    {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                ]
            )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift(window_hours=72)

        # Note: window_hours no resultado é o argumento passado, não usado nas chamadas internas
        assert result["window_hours"] == 72

    @pytest.mark.asyncio
    async def test_detect_drift_on_error_returns_error_dict(self, drift_detector):
        """Testa tratamento de erro em detect_drift."""
        drift_detector.db.plan_approvals.aggregate = Mock(
            side_effect=Exception("DB Connection failed")
        )

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is False
        assert "error" in result
        assert "last_updated" in result
        assert result["error"] == "DB Connection failed"


# =============================================================================
# Testes: DriftDetector - Publish Drift Alert
# =============================================================================


class TestPublishDriftAlert:
    """Testes para publish_drift_alert."""

    @pytest.mark.asyncio
    async def test_publish_drift_alert_success(self, drift_detector, mock_kafka_producer):
        """Testa publicação de alerta com sucesso."""
        drift_data = {
            "model_version": "v1.0.0",
            "drift_detected": True,
            "alerts": [{"metric": "avg_confidence", "change": -0.15, "threshold": 0.10}],
            "current": {"avg_confidence": 0.65},
            "baseline": {"avg_confidence": 0.80},
        }

        result = await drift_detector.publish_drift_alert(drift_data)

        assert result is True
        mock_kafka_producer.produce_and_wait.assert_called_once()

        # Verifica argumentos da chamada
        call_args = mock_kafka_producer.produce_and_wait.call_args
        assert call_args[1]["topic"] == "ml.model_drift_detected"
        assert call_args[1]["key"] == "drift_alert"

    @pytest.mark.asyncio
    async def test_publish_drift_alert_without_kafka(self, drift_detector):
        """Testa publicação sem Kafka configurado."""
        drift_detector.kafka_producer = None

        drift_data = {"model_version": "v1.0.0", "drift_detected": True}

        result = await drift_detector.publish_drift_alert(drift_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_drift_alert_on_kafka_error(self, drift_detector):
        """Testa tratamento de erro ao publicar no Kafka."""
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock(side_effect=Exception("Kafka connection error"))
        drift_detector.kafka_producer = mock_kafka

        drift_data = {"model_version": "v1.0.0", "drift_detected": True}

        result = await drift_detector.publish_drift_alert(drift_data)

        assert result is False


# =============================================================================
# Testes: DriftDetector - Get Drift Metrics
# =============================================================================


class TestGetDriftMetrics:
    """Testes para get_drift_metrics."""

    @pytest.mark.asyncio
    async def test_get_drift_metrics_includes_recommendation(self, drift_detector):
        """Testa que métricas incluem recomendação quando há drift."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 100}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.70,
                            "avg_confidence": 0.60,  # Drift detectado
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.get_drift_metrics()

        assert result["drift_detected"] is True
        assert "recommendation" in result
        assert "retraining" in result["recommendation"]

    @pytest.mark.asyncio
    async def test_get_drift_metrics_without_drift(self, drift_detector):
        """Testa que métricas sem drift não têm recomendação."""

        def mock_aggregate(window_hours):
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(
                return_value=[
                    {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                ]
            )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.get_drift_metrics()

        assert result["drift_detected"] is False
        assert "recommendation" not in result


# =============================================================================
# Testes: CanaryDeployer - Inicialização
# =============================================================================


class TestCanaryDeployerInitialization:
    """Testes para inicialização do CanaryDeployer."""

    def test_canary_deployer_initialization_defaults(self):
        """Testa inicialização com valores padrão."""
        mock_repo = Mock()
        mock_kafka = Mock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        assert deployer.model_repo == mock_repo
        assert deployer.kafka_producer == mock_kafka
        assert deployer.canary_duration_minutes == 60
        assert deployer.canary_traffic_percentage == 10

    def test_canary_deployer_initialization_custom(self):
        """Testa inicialização com valores personalizados."""
        mock_repo = Mock()
        mock_kafka = Mock()

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka,
            canary_duration_minutes=120,
            canary_traffic_percentage=20,
        )

        assert deployer.canary_duration_minutes == 120
        assert deployer.canary_traffic_percentage == 20

    def test_canary_deployer_class_has_active_canaries_dict(self):
        """Testa que a classe mantém dicionário de canaries ativos."""
        assert hasattr(CanaryDeployer, "_active_canaries")
        assert isinstance(CanaryDeployer._active_canaries, dict)


# =============================================================================
# Testes: CanaryDeployer - Start Canary
# =============================================================================


class TestCanaryDeployerStartCanary:
    """Testes para start_canary."""

    @pytest.mark.asyncio
    async def test_start_canary_success(self):
        """Testa início bem-sucedido de canary."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        result = await deployer.start_canary("v2.0.0", "v1.0.0")

        assert result["status"] == "running"
        assert "canary_id" in result
        assert result["canary_traffic_percentage"] == 10
        assert result["duration_minutes"] == 60

    @pytest.mark.asyncio
    async def test_start_canary_version_not_found(self):
        """Testa início de canary com versão não encontrada."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value=None)
        mock_kafka = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        result = await deployer.start_canary("v2.0.0", "v1.0.0")

        assert result["status"] == "failed"
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_start_canary_stores_in_active_canaries(self):
        """Testa que canary é armazenado em _active_canaries."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        result = await deployer.start_canary("v2.0.0", "v1.0.0")
        canary_id = result["canary_id"]

        assert canary_id in CanaryDeployer._active_canaries
        assert CanaryDeployer._active_canaries[canary_id]["status"] == "running"
        assert CanaryDeployer._active_canaries[canary_id]["version"] == "v2.0.0"


# =============================================================================
# Testes: CanaryDeployer - Collect Canary Metrics
# =============================================================================


class TestCanaryDeployerCollectMetrics:
    """Testes para collect_canary_metrics."""

    @pytest.mark.asyncio
    async def test_collect_canary_metrics_success(self):
        """Testa coleta de métricas de canary."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        # Primeiro cria um canary
        start_result = await deployer.start_canary("v2.0.0", "v1.0.0")
        canary_id = start_result["canary_id"]

        # Define baseline_f1
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.73

        # Coleta métricas
        result = await deployer.collect_canary_metrics(canary_id)

        assert result["canary_id"] == canary_id
        assert "metrics" in result
        assert "baseline" in result["metrics"]
        assert "canary" in result["metrics"]
        assert "comparison" in result["metrics"]
        assert result["metrics"]["canary"]["f1_score"] == 0.75  # baseline + 0.02

    @pytest.mark.asyncio
    async def test_collect_canary_metrics_not_found(self):
        """Testa coleta de canary inexistente."""
        mock_repo = MagicMock()
        mock_kafka = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        result = await deployer.collect_canary_metrics("nonexistent-canary")

        assert result["canary_id"] == "nonexistent-canary"
        assert "error" in result
        assert "not found" in result["error"]


# =============================================================================
# Testes: CanaryDeployer - Validate Canary
# =============================================================================


class TestCanaryDeployerValidateCanary:
    """Testes para validate_canary."""

    @pytest.mark.asyncio
    async def test_validate_canary_should_promote(self):
        """Testa validação que recomenda promoção."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        # Cria canary com métricas boas
        await deployer.start_canary("v2.0.0", "v1.0.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.73

        # Modifica collect_canary_metrics para retornar métricas melhores
        async def mock_collect(canary_id_param):
            return {
                "canary_id": canary_id_param,
                "metrics": {
                    "baseline": {"f1_score": 0.73, "sample_count": 1000},
                    "canary": {"f1_score": 0.78, "sample_count": 100},  # Melhorou
                    "comparison": {"f1_delta": 0.05},
                },
            }

        deployer.collect_canary_metrics = mock_collect

        result = await deployer.validate_canary(canary_id)

        assert result["should_promote"] is True
        assert any("F1 score improved" in r for r in result["reasons"])

    @pytest.mark.asyncio
    async def test_validate_canary_insufficient_samples(self):
        """Testa validação com samples insuficientes."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        # Cria canary
        await deployer.start_canary("v2.0.0", "v1.0.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.73

        # Mock com poucos samples
        async def mock_collect(canary_id_param):
            return {
                "canary_id": canary_id_param,
                "metrics": {
                    "baseline": {"f1_score": 0.73, "sample_count": 1000},
                    "canary": {"f1_score": 0.78, "sample_count": 20},  # Apenas 20 samples
                    "comparison": {"f1_delta": 0.05},
                },
            }

        deployer.collect_canary_metrics = mock_collect

        result = await deployer.validate_canary(canary_id)

        assert result["should_promote"] is False
        assert any("Insufficient samples" in r for r in result["reasons"])

    @pytest.mark.asyncio
    async def test_validate_canary_f1_degraded(self):
        """Testa validação quando F1 degradou."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0.0", "v1.0.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.73

        # Mock com F1 pior
        async def mock_collect(canary_id_param):
            return {
                "canary_id": canary_id_param,
                "metrics": {
                    "baseline": {"f1_score": 0.73, "sample_count": 1000},
                    "canary": {"f1_score": 0.68, "sample_count": 100},
                    "comparison": {"f1_delta": -0.05},
                },
            }

        deployer.collect_canary_metrics = mock_collect

        result = await deployer.validate_canary(canary_id)

        assert result["should_promote"] is False
        assert any("F1 score degraded" in r for r in result["reasons"])

    @pytest.mark.asyncio
    async def test_validate_canary_not_found(self):
        """Testa validação de canary inexistente."""
        mock_repo = MagicMock()
        mock_kafka = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        result = await deployer.validate_canary("nonexistent")

        assert result["should_promote"] is False
        assert "not found" in result["reasons"][0]  # "Canary not found"


# =============================================================================
# Testes: CanaryDeployer - Promote or Rollback
# =============================================================================


class TestCanaryDeployerPromoteOrRollback:
    """Testes para promote_or_rollback."""

    @pytest.mark.asyncio
    async def test_promote_or_rollback_promotes(self):
        """Testa promoção quando should_promote=True."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0.0"})
        mock_repo.promote_model = AsyncMock(return_value=True)
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0.0", "v1.0.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        result = await deployer.promote_or_rollback(canary_id, should_promote=True)

        assert result["status"] == "promoted"
        assert result["version"] == "v2.0.0"

    @pytest.mark.asyncio
    async def test_promote_or_rollback_rolls_back(self):
        """Testa rollback quando should_promote=False."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0.0", "v1.0.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        result = await deployer.promote_or_rollback(canary_id, should_promote=False)

        assert result["status"] == "rolled_back"
        assert result["remained_version"] == "v1.0.0"


# =============================================================================
# Testes: CanaryDeployer - Calculate Traffic Split
# =============================================================================


class TestCanaryDeployerCalculateTrafficSplit:
    """Testes para _calculate_traffic_split."""

    @pytest.mark.asyncio
    async def test_calculate_traffic_split_default(self):
        """Testa cálculo de split com valores padrão."""
        mock_repo = Mock()
        mock_kafka = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        result = await deployer._calculate_traffic_split("v2.0.0", "v1.0.0")

        assert result["canary_version"] == "v2.0.0"
        assert result["baseline_version"] == "v1.0.0"
        assert result["canary_percentage"] == 10
        assert result["baseline_percentage"] == 90

    @pytest.mark.asyncio
    async def test_calculate_traffic_split_custom_percentage(self):
        """Testa cálculo de split com percentual customizado."""
        mock_repo = Mock()
        mock_kafka = AsyncMock()

        deployer = CanaryDeployer(
            model_repo=mock_repo, kafka_producer=mock_kafka, canary_traffic_percentage=25
        )

        result = await deployer._calculate_traffic_split("v2.0.0", "v1.0.0")

        assert result["canary_percentage"] == 25
        assert result["baseline_percentage"] == 75


# =============================================================================
# Testes: DriftDetector - Testes de Integração Reduzindo Mocks
# =============================================================================


class TestDriftDetectorRealLogic:
    """Testes que exercitam lógica real reduzindo mocks."""

    def test_build_aggregation_pipeline_real_logic(self, drift_detector):
        """Testa pipeline de agregação sem mock - executa lógica real."""
        window_hours = 24
        pipeline = drift_detector._build_aggregation_pipeline(window_hours)

        # Verifica estrutura completa do pipeline
        assert len(pipeline) == 2
        assert "$match" in pipeline[0]
        assert "$group" in pipeline[1]

        # Verifica campos do $match
        match_stage = pipeline[0]["$match"]
        assert "created_at" in match_stage
        assert "$gte" in match_stage["created_at"]

        # Verifica campos do $group
        group_stage = pipeline[1]["$group"]
        assert group_stage["_id"] is None
        assert "approve_rate" in group_stage
        assert "avg_confidence" in group_stage
        assert "count" in group_stage

        # Verifica lógica do approve_rate ($avg com $cond)
        approve_rate_expr = group_stage["approve_rate"]
        assert "$avg" in approve_rate_expr
        assert "$cond" in approve_rate_expr["$avg"]
        cond = approve_rate_expr["$avg"]["$cond"]
        assert len(cond) == 3  # [if, then, else]

    def test_build_aggregation_pipeline_different_windows(self, drift_detector):
        """Testa pipeline com diferentes janelas de tempo."""
        # Testa múltiplas janelas
        for window in [1, 6, 24, 48, 168, 720]:
            pipeline = drift_detector._build_aggregation_pipeline(window)
            match_since = pipeline[0]["$match"]["created_at"]["$gte"]
            expected = datetime.now(timezone.utc) - timedelta(hours=window)
            # Verifica que timestamp está correto (±5 segundos tolerância)
            time_diff = abs((expected - match_since).total_seconds())
            assert time_diff < 5, f"Janela {window}h produziu timestamp incorreto"

    @pytest.mark.asyncio
    async def test_detect_drift_change_calculation_logic(self, drift_detector):
        """Testa cálculo de mudanças sem mock excessivo."""
        # Setup mínimo - apenas mock de aggregate
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            # Retorna cursor mockado
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.80, "avg_confidence": 0.85, "count": 500}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.60,  # Queda de 0.20
                            "avg_confidence": 0.70,  # Queda de 0.15
                            "count": 100,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(
            return_value={"version": "v1.5.0", "stage": "production", "is_active": True}
        )

        result = await drift_detector.detect_drift()

        # Verifica cálculos de mudança
        baseline = result["baseline"]
        current = result["current"]

        # Confidence: 0.70 - 0.85 = -0.15
        assert abs(current["avg_confidence"] - baseline["avg_confidence"]) == pytest.approx(0.15)

        # Approve rate: 0.60 - 0.80 = -0.20
        assert abs(current["approve_rate"] - baseline["approve_rate"]) == pytest.approx(0.20)

        # Ambos drifts detectados
        assert result["drift_detected"] is True
        assert len(result["alerts"]) == 2

        # Verifica severidade calculada (confidence 0.15 > 0.10 * 1.5 = 0.15 → critical)
        confidence_alert = next(a for a in result["alerts"] if a["metric"] == "avg_confidence")
        assert confidence_alert["severity"] == "critical"
        assert confidence_alert["change"] == -0.15

    @pytest.mark.asyncio
    async def test_detect_drift_edge_case_zero_baseline(self, drift_detector):
        """Testa detecção quando baseline tem zero samples."""
        # Baseline vazio, current com dados
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline vazio
                mock_cursor.to_list = AsyncMock(return_value=[])
            else:  # current com dados
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 50}
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0"})

        result = await drift_detector.detect_drift()

        # Quando baseline está vazio, usa valores padrão
        assert result["baseline"]["sample_count"] == 0
        assert result["baseline"]["approve_rate"] == 0.65  # valor padrão


# =============================================================================
# Testes: CanaryDeployer - Testes de Lógica Real
# =============================================================================


class TestCanaryDeployerRealLogic:
    """Testes que exercitam lógica real do CanaryDeployer."""

    @pytest.mark.asyncio
    async def test_publish_canary_event_without_kafka(self):
        """Testa _publish_canary_event sem Kafka (caminho silencioso)."""
        deployer = CanaryDeployer(model_repo=Mock(), kafka_producer=None)  # Sem Kafka

        # Não deve lançar erro
        await deployer._publish_canary_event("canary_started", "cid", "v2", "v1")

    @pytest.mark.asyncio
    async def test_publish_canary_event_kafka_error(self):
        """Testa tratamento de erro ao publicar evento canary."""
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock(side_effect=Exception("Kafka down"))

        deployer = CanaryDeployer(model_repo=Mock(), kafka_producer=mock_kafka)

        # Não deve lançar erro - trata exceção internamente
        await deployer._publish_canary_event("canary_started", "cid", "v2", "v1")

    @pytest.mark.asyncio
    async def test_promote_nonexistent_canary(self):
        """Testa promoção de canary inexistente."""
        mock_repo = Mock()
        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=AsyncMock())

        result = await deployer._promote("nonexistent-canary")

        assert result["status"] == "failed"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_canary(self):
        """Testa rollback de canary inexistente."""
        deployer = CanaryDeployer(model_repo=Mock(), kafka_producer=AsyncMock())

        result = await deployer._rollback("nonexistent-canary")

        assert result["status"] == "failed"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_promote_with_repo_failure(self):
        """Testa promoção quando repositório falha."""
        mock_repo = MagicMock()
        mock_repo.promote_model = AsyncMock(return_value=False)  # Falha na promoção
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        # Cria canary
        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        result = await deployer._promote(canary_id)

        assert result["status"] == "failed"
        assert "Promotion failed" in result["error"]

    @pytest.mark.asyncio
    async def test_promote_success_updates_canary_state(self):
        """Testa que promoção bem-sucedida atualiza estado do canary."""
        mock_repo = MagicMock()
        mock_repo.promote_model = AsyncMock(return_value=True)
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        # Cria canary
        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        # Promove
        result = await deployer._promote(canary_id)

        # Verifica estado atualizado
        canary = CanaryDeployer._active_canaries[canary_id]
        assert canary["status"] == "promoted"
        assert "completed_at" in canary

        assert result["status"] == "promoted"
        assert result["version"] == "v2.0"
        assert result["previous_version"] == "v1.0"

    @pytest.mark.asyncio
    async def test_rollback_updates_canary_state(self):
        """Testa que rollback atualiza estado do canary."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        # Cria canary
        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        # Rollback
        result = await deployer._rollback(canary_id)

        # Verifica estado atualizado
        canary = CanaryDeployer._active_canaries[canary_id]
        assert canary["status"] == "rolled_back"
        assert "completed_at" in canary

        assert result["status"] == "rolled_back"
        assert result["remained_version"] == "v1.0"

    @pytest.mark.asyncio
    async def test_collect_canary_metrics_uses_baseline_f1(self):
        """Testa que collect_canary_metrics usa baseline_f1 do canary."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        # Cria canary
        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        # Define baseline_f1 diferente
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.80

        result = await deployer.collect_canary_metrics(canary_id)

        # canary_f1 = baseline_f1 + 0.02 = 0.82
        assert result["metrics"]["baseline"]["f1_score"] == 0.80
        assert result["metrics"]["canary"]["f1_score"] == pytest.approx(0.82)
        assert result["metrics"]["comparison"]["f1_delta"] == pytest.approx(0.02)

    @pytest.mark.asyncio
    async def test_validate_canary_with_marginal_improvement(self):
        """Testa validação com melhoria marginal (< 0.01)."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.73

        # Mock com melhoria marginal
        async def mock_collect(cid):
            return {
                "canary_id": cid,
                "metrics": {
                    "baseline": {"f1_score": 0.73, "sample_count": 1000},
                    "canary": {"f1_score": 0.735, "sample_count": 100},  # delta = 0.005
                    "comparison": {"f1_delta": 0.005},
                },
            }

        deployer.collect_canary_metrics = mock_collect

        result = await deployer.validate_canary(canary_id)

        # Deve promover (marginal ainda é positivo) mas com warning
        assert result["should_promote"] is True
        assert any("marginal" in r.lower() for r in result["reasons"])

    @pytest.mark.asyncio
    async def test_validate_canary_exactly_at_threshold(self):
        """Testa validação exatamente no threshold de samples."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.73

        # Mock com exatamente min_samples
        async def mock_collect(cid):
            return {
                "canary_id": cid,
                "metrics": {
                    "baseline": {"f1_score": 0.73, "sample_count": 1000},
                    "canary": {"f1_score": 0.75, "sample_count": 50},  # Exatamente min_samples
                    "comparison": {"f1_delta": 0.02},
                },
            }

        deployer.collect_canary_metrics = mock_collect

        result = await deployer.validate_canary(canary_id)

        # 50 >= min_samples (50), então deve promover
        assert result["should_promote"] is True

    @pytest.mark.asyncio
    async def test_promote_or_rollback_integration(self):
        """Testa fluxo completo de promoção/rollback."""
        mock_repo = MagicMock()
        mock_repo.promote_model = AsyncMock(return_value=True)
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        # Testa promoção
        await deployer.start_canary("v2.0", "v1.0")
        canary_id_1 = list(CanaryDeployer._active_canaries.keys())[-1]
        result_promote = await deployer.promote_or_rollback(canary_id_1, should_promote=True)
        assert result_promote["status"] == "promoted"

        # Testa rollback
        await deployer.start_canary("v3.0", "v2.0")
        canary_id_2 = list(CanaryDeployer._active_canaries.keys())[-1]
        result_rollback = await deployer.promote_or_rollback(canary_id_2, should_promote=False)
        assert result_rollback["status"] == "rolled_back"


# =============================================================================
# Testes: DriftDetector - Error Handling Paths
# =============================================================================


class TestDriftDetectorErrorHandling:
    """Testes para caminhos de erro não cobertos."""

    @pytest.mark.asyncio
    async def test_calculate_current_exception_handling(self, drift_detector):
        """Testa tratamento de exceção em calculate_current."""
        drift_detector.db.plan_approvals.aggregate = Mock(
            side_effect=Exception("Connection timeout")
        )

        with pytest.raises(Exception, match="Connection timeout"):
            await drift_detector.calculate_current()

    @pytest.mark.asyncio
    async def test_get_active_model_version_database_error(self, drift_detector):
        """Testa busca de versão ativa com erro de banco."""
        drift_detector.db.model_versions.find_one = Mock(
            side_effect=Exception("Database unavailable")
        )

        version = await drift_detector._get_active_model_version()

        # Deve retornar "unknown" em caso de erro
        assert version == "unknown"

    @pytest.mark.asyncio
    async def test_get_active_model_version_without_version_field(self, drift_detector):
        """Testa busca quando documento não tem campo 'version'."""
        drift_detector.db.model_versions.find_one = AsyncMock(
            return_value={"stage": "production", "is_active": True}  # Sem 'version'
        )

        version = await drift_detector._get_active_model_version()

        assert version == "unknown"

    @pytest.mark.asyncio
    async def test_publish_drift_alert_serialization_error(self, drift_detector):
        """Testa tratamento de erro ao serializar dados do alerta."""
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock(side_effect=TypeError("Cannot serialize"))
        drift_detector.kafka_producer = mock_kafka

        result = await drift_detector.publish_drift_alert(
            {"model_version": "v1.0", "drift_detected": True, "alerts": [{"metric": "test"}]}
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_detect_drift_with_calculate_current_error(self, drift_detector):
        """Testa detect_drift quando calculate_current falha."""
        # Baseline ok, current falha
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline ok
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                    ]
                )
            else:  # current falha
                raise Exception("Current calculation failed")
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate

        result = await drift_detector.detect_drift()

        # Deve retornar dict de erro
        assert result["drift_detected"] is False
        assert "error" in result
        assert "Current calculation failed" in result["error"]


# =============================================================================
# Testes: CanaryDeployer - Edge Cases e Lógica de Negócio
# =============================================================================


class TestCanaryDeployerEdgeCases:
    """Testes para casos extremos e lógica de negócio."""

    @pytest.mark.asyncio
    async def test_start_canary_with_same_versions(self):
        """Testa start_canary quando versões são iguais."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v1.0"})
        mock_kafka = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        # Versões iguais não deve causar erro
        result = await deployer.start_canary("v1.0", "v1.0")

        # Deve criar canary mesmo assim
        assert result["status"] == "running"
        assert "canary_id" in result

    @pytest.mark.asyncio
    async def test_collect_canary_metrics_without_baseline_f1(self):
        """Testa coleta de métricas quando baseline_f1 não foi definido."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        # Remove baseline_f1 (valor padrão é 0.73 no código)
        if "baseline_f1" in CanaryDeployer._active_canaries[canary_id]:
            del CanaryDeployer._active_canaries[canary_id]["baseline_f1"]

        result = await deployer.collect_canary_metrics(canary_id)

        # Deve usar valor padrão (0.73)
        assert result["metrics"]["baseline"]["f1_score"] == 0.73
        assert result["metrics"]["canary"]["f1_score"] == 0.75  # 0.73 + 0.02

    def test_active_canaries_is_class_variable(self):
        """Testa que _active_canaries é compartilhado entre instâncias."""
        CanaryDeployer._active_canaries.clear()

        deployer1 = CanaryDeployer(model_repo=Mock(), kafka_producer=Mock())
        deployer2 = CanaryDeployer(model_repo=Mock(), kafka_producer=Mock())

        # Ambas instâncias compartilham o mesmo dict
        assert deployer1._active_canaries is deployer2._active_canaries

    @pytest.mark.asyncio
    async def test_validate_canary_empty_comparison_metrics(self):
        """Testa validação quando comparison está vazio."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        # Mock retorna comparison vazio
        async def mock_collect(cid):
            return {
                "canary_id": cid,
                "metrics": {
                    "baseline": {"f1_score": 0.73, "sample_count": 1000},
                    "canary": {"f1_score": 0.75, "sample_count": 100},
                    "comparison": {},  # Vazio
                },
            }

        deployer.collect_canary_metrics = mock_collect

        result = await deployer.validate_canary(canary_id)

        # f1_delta = 0 (default do dict), deve promover se samples >= 50
        assert result["should_promote"] is True
        assert result["metrics_summary"]["f1_delta"] == 0


# =============================================================================
# Testes: DriftDetector - Cobertura Adicional com Menos Mocks
# =============================================================================


class TestDriftDetectorAdditionalCoverage:
    """Testes adicionais para aumentar cobertura reduzindo mocks."""

    def test_drift_detector_init_with_minimal_params(self):
        """Testa inicialização com parâmetros mínimos."""
        mock_db = Mock()
        detector = DriftDetector(mongo_client=mock_db, kafka_producer=None)

        assert detector.mongo_client == mock_db
        assert detector.kafka_producer is None
        assert detector.confidence_threshold == 0.10
        assert detector.approve_rate_threshold == 0.15
        assert detector.baseline_window_hours == 168

    def test_drift_detector_init_with_all_params(self):
        """Testa inicialização com todos os parâmetros."""
        mock_db = Mock()
        mock_kafka = AsyncMock()
        detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka,
            confidence_threshold=0.20,
            approve_rate_threshold=0.25,
            baseline_window_hours=48,
        )

        assert detector.confidence_threshold == 0.20
        assert detector.approve_rate_threshold == 0.25
        assert detector.baseline_window_hours == 48

    @pytest.mark.asyncio
    async def test_calculate_baseline_with_valid_results(self, drift_detector):
        """Testa calculate_baseline retornando resultados válidos."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"_id": None, "approve_rate": 0.75, "avg_confidence": 0.80, "count": 200}]
        )
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        result = await drift_detector.calculate_baseline(168)

        assert result["approve_rate"] == 0.75
        assert result["avg_confidence"] == 0.80
        assert result["sample_count"] == 200

    @pytest.mark.asyncio
    async def test_calculate_baseline_with_missing_fields(self, drift_detector):
        """Testa calculate_baseline com campos faltando."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": None,
                    "count": 50,
                    # approve_rate e avg_confidence faltando
                }
            ]
        )
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        result = await drift_detector.calculate_baseline(168)

        # get() retorna 0.0 como padrão
        assert result["approve_rate"] == 0.0
        assert result["avg_confidence"] == 0.0
        assert result["sample_count"] == 50

    @pytest.mark.asyncio
    async def test_calculate_current_with_valid_data(self, drift_detector):
        """Testa calculate_current com dados válidos."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"_id": None, "approve_rate": 0.65, "avg_confidence": 0.70, "count": 75}]
        )
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        result = await drift_detector.calculate_current(24)

        assert result["approve_rate"] == 0.65
        assert result["avg_confidence"] == 0.70
        assert result["sample_count"] == 75

    @pytest.mark.asyncio
    async def test_detect_drift_critical_severity_boundary(self, drift_detector):
        """Testa detecção de drift com severidade crítica no limite."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 100}
                    ]
                )
            else:  # current - mudança de 0.15 (exatamente 1.5x threshold)
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.70,
                            "avg_confidence": 0.65,  # Queda de 0.15 = 1.5 * 0.10
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(
            return_value={"version": "v1.0", "stage": "production"}
        )

        result = await drift_detector.detect_drift()

        # 0.15 >= 0.15 é "critical" (condição é >= no código)
        assert result["drift_detected"] is True
        confidence_alert = next(a for a in result["alerts"] if a["metric"] == "avg_confidence")
        assert confidence_alert["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_detect_drift_above_critical_threshold(self, drift_detector):
        """Testa detecção acima do threshold crítico."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 100}
                    ]
                )
            else:  # current - mudança de 0.16 (acima de 1.5x threshold)
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.70,
                            "avg_confidence": 0.64,  # Queda de 0.16 > 1.5 * 0.10
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(
            return_value={"version": "v1.0", "stage": "production"}
        )

        result = await drift_detector.detect_drift()

        confidence_alert = next(a for a in result["alerts"] if a["metric"] == "avg_confidence")
        assert confidence_alert["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_detect_drift_does_not_alert_when_below_threshold(self, drift_detector):
        """Testa que não há alerta quando mudança é abaixo do threshold."""

        def mock_aggregate(pipeline):
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(
                return_value=[
                    {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                ]
            )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(
            return_value={"version": "v1.0", "stage": "production"}
        )

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is False
        assert len(result["alerts"]) == 0

    @pytest.mark.asyncio
    async def test_detect_drift_includes_model_version(self, drift_detector):
        """Testa que detect_drift inclui versão do modelo."""

        def mock_aggregate(pipeline):
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(
                return_value=[
                    {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                ]
            )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(
            return_value={"version": "v2.1.0", "stage": "production", "is_active": True}
        )

        result = await drift_detector.detect_drift()

        assert result["model_version"] == "v2.1.0"

    @pytest.mark.asyncio
    async def test_get_active_model_version_returns_version(self, drift_detector):
        """Testa _get_active_model_version retornando versão."""
        drift_detector.db.model_versions.find_one = AsyncMock(
            return_value={"version": "v3.0.0", "stage": "production", "is_active": True}
        )

        version = await drift_detector._get_active_model_version()

        assert version == "v3.0.0"

    @pytest.mark.asyncio
    async def test_get_active_model_version_empty_doc(self, drift_detector):
        """Testa _get_active_model_version com documento vazio."""
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={})

        version = await drift_detector._get_active_model_version()

        assert version == "unknown"

    @pytest.mark.asyncio
    async def test_publish_drift_alert_without_producer(self, drift_detector):
        """Testa publish_drift_alert sem producer Kafka."""
        drift_detector.kafka_producer = None

        result = await drift_detector.publish_drift_alert(
            {
                "model_version": "v1.0",
                "drift_detected": True,
                "current": {"avg_confidence": 0.65},
                "baseline": {"avg_confidence": 0.80},
            }
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_drift_alert_with_producer(self, drift_detector, mock_kafka_producer):
        """Testa publish_drift_alert com producer Kafka."""
        drift_data = {
            "model_version": "v1.5.0",
            "drift_detected": True,
            "alerts": [{"metric": "avg_confidence", "change": -0.15}],
            "current": {"avg_confidence": 0.65},
            "baseline": {"avg_confidence": 0.80},
        }

        result = await drift_detector.publish_drift_alert(drift_data)

        assert result is True
        mock_kafka_producer.produce_and_wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_drift_metrics_no_drift(self, drift_detector):
        """Testa get_drift_metrics quando não há drift."""

        def mock_aggregate(pipeline):
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(
                return_value=[
                    {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                ]
            )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0"})

        result = await drift_detector.get_drift_metrics()

        assert result["drift_detected"] is False
        assert "recommendation" not in result


# =============================================================================
# Testes: CanaryDeployer - Cobertura Adicional
# =============================================================================


class TestCanaryDeployerAdditionalCoverage:
    """Testes adicionais para CanaryDeployer."""

    def test_canary_deployer_init(self):
        """Testa inicialização do CanaryDeployer."""
        mock_repo = Mock()
        mock_kafka = AsyncMock()

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka,
            canary_duration_minutes=90,
            canary_traffic_percentage=15,
        )

        assert deployer.model_repo == mock_repo
        assert deployer.kafka_producer == mock_kafka
        assert deployer.canary_duration_minutes == 90
        assert deployer.canary_traffic_percentage == 15

    @pytest.mark.asyncio
    async def test_calculate_traffic_split_returns_percentages(self):
        """Testa _calculate_traffic_split retorna percentuais corretos."""
        deployer = CanaryDeployer(
            model_repo=Mock(), kafka_producer=AsyncMock(), canary_traffic_percentage=20
        )

        result = await deployer._calculate_traffic_split("v3.0", "v2.0")

        assert result["canary_version"] == "v3.0"
        assert result["baseline_version"] == "v2.0"
        assert result["canary_percentage"] == 20
        assert result["baseline_percentage"] == 80

    @pytest.mark.asyncio
    async def test_start_canary_returns_status(self):
        """Testa start_canary retorna status correto."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka,
            canary_duration_minutes=120,
            canary_traffic_percentage=25,
        )

        result = await deployer.start_canary("v2.0", "v1.0")

        assert result["status"] == "running"
        assert "canary_id" in result
        assert result["canary_traffic_percentage"] == 25
        assert result["duration_minutes"] == 120
        assert "started_at" in result

    @pytest.mark.asyncio
    async def test_collect_canary_metrics_returns_structure(self):
        """Testa collect_canary_metrics retorna estrutura correta."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        result = await deployer.collect_canary_metrics(canary_id)

        assert "canary_id" in result
        assert "metrics" in result
        assert "baseline" in result["metrics"]
        assert "canary" in result["metrics"]
        assert "comparison" in result["metrics"]
        assert "collected_at" in result

    @pytest.mark.asyncio
    async def test_validate_canary_returns_structure(self):
        """Testa validate_canary retorna estrutura correta."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.73

        result = await deployer.validate_canary(canary_id)

        assert "should_promote" in result
        assert "reasons" in result
        assert "metrics_summary" in result
        assert isinstance(result["reasons"], list)

    @pytest.mark.asyncio
    async def test_promote_or_rollback_returns_status(self):
        """Testa promote_or_rollback retorna status correto."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_repo.promote_model = AsyncMock(return_value=True)
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        result = await deployer.promote_or_rollback(canary_id, should_promote=True)

        assert result["status"] == "promoted"
        assert "canary_id" in result
        assert "version" in result


# =============================================================================
# Testes: DriftDetector - Cobertura de Métodos Internos
# =============================================================================


class TestDriftDetectorInternalMethods:
    """Testes para métodos internos e lógica de negócio."""

    def test_db_property(self, drift_detector):
        """Testa property db retorna mongo_client."""
        assert drift_detector.db is drift_detector.mongo_client

    def test_aggregation_pipeline_approve_rate_logic(self, drift_detector):
        """Testa lógica de cálculo de approve_rate no pipeline."""
        pipeline = drift_detector._build_aggregation_pipeline(24)

        # Verifica estrutura do $cond no approve_rate
        group_stage = pipeline[1]["$group"]
        approve_rate_expr = group_stage["approve_rate"]
        cond_expr = approve_rate_expr["$avg"]["$cond"]

        # $cond: [if, then, else]
        assert len(cond_expr) == 3
        # if: $eq:["$approval_decision", "approve"]
        assert "$eq" in cond_expr[0]
        assert cond_expr[0]["$eq"][1] == "approve"
        # then: 1
        assert cond_expr[1] == 1
        # else: 0
        assert cond_expr[2] == 0

    def test_aggregation_pipeline_avg_confidence(self, drift_detector):
        """Testa cálculo de avg_confidence no pipeline."""
        pipeline = drift_detector._build_aggregation_pipeline(24)

        group_stage = pipeline[1]["$group"]
        assert group_stage["avg_confidence"] == {"$avg": "$ml_confidence"}

    def test_aggregation_pipeline_count(self, drift_detector):
        """Testa contagem no pipeline."""
        pipeline = drift_detector._build_aggregation_pipeline(24)

        group_stage = pipeline[1]["$group"]
        assert group_stage["count"] == {"$sum": 1}

    def test_aggregation_pipeline_group_id_none(self, drift_detector):
        """Testa que _id no group é None (agrega todos)."""
        pipeline = drift_detector._build_aggregation_pipeline(24)

        group_stage = pipeline[1]["$group"]
        assert group_stage["_id"] is None

    @pytest.mark.asyncio
    async def test_calculate_baseline_calls_aggregate(self, drift_detector):
        """Testa que calculate_baseline chama aggregate com pipeline correto."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}]
        )
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        await drift_detector.calculate_baseline(48)

        # Verifica que aggregate foi chamado
        drift_detector.db.plan_approvals.aggregate.assert_called_once()
        # Verifica que o pipeline foi construído
        call_args = drift_detector.db.plan_approvals.aggregate.call_args
        pipeline = call_args[0][0]
        assert isinstance(pipeline, list)
        assert len(pipeline) == 2

    @pytest.mark.asyncio
    async def test_calculate_current_calls_aggregate(self, drift_detector):
        """Testa que calculate_current chama aggregate."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"_id": None, "approve_rate": 0.65, "avg_confidence": 0.70, "count": 50}]
        )
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)

        await drift_detector.calculate_current(12)

        drift_detector.db.plan_approvals.aggregate.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_drift_calls_calculate_methods(self, drift_detector):
        """Testa que detect_drift chama calculate_baseline e calculate_current."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}]
        )
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0"})

        # Spy nos métodos
        with pytest.MonkeyPatch.context() as m:
            baseline_called = [False]
            current_called = [False]

            original_baseline = drift_detector.calculate_baseline
            original_current = drift_detector.calculate_current

            async def spy_baseline(window):
                baseline_called[0] = True
                return await original_baseline(window)

            async def spy_current(window):
                current_called[0] = True
                return await original_current(window)

            m.setattr(drift_detector, "calculate_baseline", spy_baseline)
            m.setattr(drift_detector, "calculate_current", spy_current)

            await drift_detector.detect_drift()

            assert baseline_called[0], "calculate_baseline deve ser chamado"
            assert current_called[0], "calculate_current deve ser chamado"

    @pytest.mark.asyncio
    async def test_detect_drift_calls_get_active_model_version(self, drift_detector):
        """Testa que detect_drift chama _get_active_model_version."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}]
        )
        drift_detector.db.plan_approvals.aggregate = Mock(return_value=mock_cursor)
        drift_detector.db.model_versions.find_one = AsyncMock(
            return_value={"version": "v2.5.0", "stage": "production", "is_active": True}
        )

        result = await drift_detector.detect_drift()

        assert result["model_version"] == "v2.5.0"

    @pytest.mark.asyncio
    async def test_detect_drift_alerts_on_confidence_threshold(self, drift_detector):
        """Testa alerta quando confidence atinge threshold."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 100}
                    ]
                )
            else:  # current
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.70,
                            "avg_confidence": 0.70,  # Queda de 0.10 (threshold)
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0"})

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is True
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["metric"] == "avg_confidence"
        assert result["alerts"][0]["change"] == -0.10

    @pytest.mark.asyncio
    async def test_detect_drift_alerts_on_approve_rate_threshold(self, drift_detector):
        """Testa alerta quando approve_rate atinge threshold."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.80, "avg_confidence": 0.75, "count": 100}
                    ]
                )
            else:  # current - approve_rate diferente
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.64,  # Queda de 0.16 (> 0.15 threshold)
                            "avg_confidence": 0.75,  # Igual ao baseline para não causar drift
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0"})

        result = await drift_detector.detect_drift()

        assert result["drift_detected"] is True
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["metric"] == "approve_rate"

    @pytest.mark.asyncio
    async def test_publish_drift_alert_constructs_event(self, drift_detector, mock_kafka_producer):
        """Testa que publish_drift_alert constrói evento corretamente."""
        drift_data = {
            "model_version": "v1.0",
            "drift_detected": True,
            "alerts": [{"metric": "avg_confidence", "change": -0.12}],
            "current": {"avg_confidence": 0.68},
            "baseline": {"avg_confidence": 0.80},
        }

        await drift_detector.publish_drift_alert(drift_data)

        # Verifica chamada ao producer
        mock_kafka_producer.produce_and_wait.assert_called_once()
        call_kwargs = mock_kafka_producer.produce_and_wait.call_args[1]
        assert call_kwargs["topic"] == "ml.model_drift_detected"
        assert call_kwargs["key"] == "drift_alert"

    @pytest.mark.asyncio
    async def test_get_drift_metrics_adds_recommendation_on_drift(self, drift_detector):
        """Testa que get_drift_metrics adiciona recomendação quando há drift."""
        call_count = [0]

        def mock_aggregate(pipeline):
            call_count[0] += 1
            mock_cursor = AsyncMock()
            if call_count[0] == 1:  # baseline
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 100}
                    ]
                )
            else:  # current com drift
                mock_cursor.to_list = AsyncMock(
                    return_value=[
                        {
                            "_id": None,
                            "approve_rate": 0.70,
                            "avg_confidence": 0.65,  # Drift de 0.15
                            "count": 50,
                        }
                    ]
                )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0"})

        result = await drift_detector.get_drift_metrics()

        assert result["drift_detected"] is True
        assert "recommendation" in result
        assert "retraining" in result["recommendation"]

    @pytest.mark.asyncio
    async def test_get_drift_metrics_no_recommendation_without_drift(self, drift_detector):
        """Testa que get_drift_metrics não adiciona recomendação sem drift."""

        def mock_aggregate(pipeline):
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(
                return_value=[
                    {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
                ]
            )
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0"})

        result = await drift_detector.get_drift_metrics()

        assert result["drift_detected"] is False
        assert "recommendation" not in result


# =============================================================================
# Testes: CanaryDeployer - Testes de Lógica Interna
# =============================================================================


class TestCanaryDeployerInternalLogic:
    """Testes para lógica interna do CanaryDeployer."""

    @pytest.mark.asyncio
    async def test_start_canary_stores_state_correctly(self):
        """Testa que start_canary armazena estado corretamente."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka,
            canary_duration_minutes=90,
            canary_traffic_percentage=20,
        )

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        canary = CanaryDeployer._active_canaries[canary_id]
        assert canary["version"] == "v2.0"
        assert canary["target_version"] == "v1.0"
        assert canary["status"] == "running"
        assert canary["traffic_percentage"] == 20
        assert canary["duration_minutes"] == 90
        assert "started_at" in canary
        assert "metrics" in canary

    @pytest.mark.asyncio
    async def test_collect_canary_metrics_calculates_delta(self):
        """Testa que collect_canary_metrics calcula delta corretamente."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.75

        result = await deployer.collect_canary_metrics(canary_id)

        # f1_delta = canary_f1 - baseline_f1 = 0.77 - 0.75 = 0.02
        assert result["metrics"]["comparison"]["f1_delta"] == pytest.approx(0.02)
        # accuracy_delta = 0.81 - 0.80 = 0.01
        assert result["metrics"]["comparison"]["accuracy_delta"] == pytest.approx(0.01)

    @pytest.mark.asyncio
    async def test_validate_canary_checks_sample_threshold(self):
        """Testa que validate_canary verifica threshold de samples."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]
        CanaryDeployer._active_canaries[canary_id]["baseline_f1"] = 0.73

        # Mock com samples abaixo do threshold (50)
        async def mock_collect(cid):
            return {
                "canary_id": cid,
                "metrics": {
                    "baseline": {"f1_score": 0.73, "sample_count": 1000},
                    "canary": {"f1_score": 0.75, "sample_count": 49},  # 49 < 50
                    "comparison": {"f1_delta": 0.02},
                },
            }

        deployer.collect_canary_metrics = mock_collect

        result = await deployer.validate_canary(canary_id)

        assert result["should_promote"] is False
        assert any("Insufficient samples" in r for r in result["reasons"])

    @pytest.mark.asyncio
    async def test_promote_updates_status_and_publishes_event(self):
        """Testa que _promote atualiza status e publica evento."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_repo.promote_model = AsyncMock(return_value=True)
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        await deployer._promote(canary_id)

        canary = CanaryDeployer._active_canaries[canary_id]
        assert canary["status"] == "promoted"
        assert "completed_at" in canary

        # Verifica que promote_model foi chamado
        mock_repo.promote_model.assert_called_once_with(
            version="v2.0", stage="production", promoted_by="canary"
        )

    @pytest.mark.asyncio
    async def test_rollback_updates_status_and_publishes_event(self):
        """Testa que _rollback atualiza status e publica evento."""
        mock_repo = MagicMock()
        mock_repo.get_model_version = AsyncMock(return_value={"version": "v2.0"})
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock()

        deployer = CanaryDeployer(model_repo=mock_repo, kafka_producer=mock_kafka)

        await deployer.start_canary("v2.0", "v1.0")
        canary_id = list(CanaryDeployer._active_canaries.keys())[-1]

        await deployer._rollback(canary_id)

        canary = CanaryDeployer._active_canaries[canary_id]
        assert canary["status"] == "rolled_back"
        assert "completed_at" in canary
