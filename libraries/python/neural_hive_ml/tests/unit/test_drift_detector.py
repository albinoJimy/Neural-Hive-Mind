"""Testes unitários para DriftDetector - Detecção de Model Drift."""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

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
        baseline_window_hours=168
    )


@pytest.fixture
def mock_aggregation_results():
    """Mock de resultados de agregação MongoDB."""
    return {
        "_id": None,
        "approve_rate": 0.70,
        "avg_confidence": 0.75,
        "count": 100
    }


# =============================================================================
# Testes: DriftDetector - Inicialização
# =============================================================================


class TestDriftDetectorInitialization:
    """Testes para inicialização do DriftDetector."""

    def test_drift_detector_initialization_with_defaults(self, mock_mongo_client):
        """Testa inicialização com valores padrão."""
        detector = DriftDetector(
            mongo_client=mock_mongo_client,
            kafka_producer=None
        )

        assert detector.mongo_client == mock_mongo_client
        assert detector.kafka_producer is None
        assert detector.confidence_threshold == 0.10
        assert detector.approve_rate_threshold == 0.15
        assert detector.baseline_window_hours == 168

    def test_drift_detector_initialization_with_custom_thresholds(self, mock_mongo_client, mock_kafka_producer):
        """Testa inicialização com thresholds personalizados."""
        detector = DriftDetector(
            mongo_client=mock_mongo_client,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.15,
            approve_rate_threshold=0.20,
            baseline_window_hours=72
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

        since = datetime.utcnow() - timedelta(hours=window_hours)
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
            "created_at": datetime.utcnow()
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
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.75,
                    "count": 100
                }])
            else:  # current
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.72,  # Diferença de 0.02 (< 0.15 threshold)
                    "avg_confidence": 0.76,  # Diferença de 0.01 (< 0.10 threshold)
                    "count": 50
                }])
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
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.70,
                    "count": 100
                }])
            else:  # current
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,  # Diferença de 0.00
                    "avg_confidence": 0.80,  # Diferença de 0.10 (exatamente threshold)
                    "count": 50
                }])
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
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.80,
                    "count": 100
                }])
            else:  # current
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.68,  # Queda de 0.12 (> 0.10 threshold, < 0.15 critical)
                    "count": 50
                }])
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
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.60,
                    "count": 100
                }])
            else:  # current
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.75,  # Aumento de 0.15 (> 0.10 threshold)
                    "count": 50
                }])
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
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.75,
                    "count": 100
                }])
            else:  # current
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.50,  # Queda de 0.20 (> 0.15 threshold)
                    "avg_confidence": 0.75,
                    "count": 50
                }])
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
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.80,
                    "count": 100
                }])
            else:  # current
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.50,  # Queda de 0.30 (> 1.5 * 0.10)
                    "count": 50
                }])
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
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.80,
                    "count": 100
                }])
            else:  # current
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.50,  # Queda de 0.20
                    "avg_confidence": 0.60,  # Queda de 0.20
                    "count": 50
                }])
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
            mock_cursor.to_list = AsyncMock(return_value=[{
                "_id": None,
                "approve_rate": 0.70,
                "avg_confidence": 0.75,
                "count": 100
            }])
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
            mock_cursor.to_list = AsyncMock(return_value=[{
                "_id": None,
                "approve_rate": 0.70,
                "avg_confidence": 0.75,
                "count": 100
            }])
            return mock_cursor

        drift_detector.db.plan_approvals.aggregate = mock_aggregate
        drift_detector.db.model_versions.find_one = AsyncMock(return_value={"version": "v1.0.0"})

        result = await drift_detector.detect_drift(window_hours=72)

        # Note: window_hours no resultado é o argumento passado, não usado nas chamadas internas
        assert result["window_hours"] == 72

    @pytest.mark.asyncio
    async def test_detect_drift_on_error_returns_error_dict(self, drift_detector):
        """Testa tratamento de erro em detect_drift."""
        drift_detector.db.plan_approvals.aggregate = Mock(side_effect=Exception("DB Connection failed"))

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
            "alerts": [
                {"metric": "avg_confidence", "change": -0.15, "threshold": 0.10}
            ],
            "current": {"avg_confidence": 0.65},
            "baseline": {"avg_confidence": 0.80}
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

        drift_data = {
            "model_version": "v1.0.0",
            "drift_detected": True
        }

        result = await drift_detector.publish_drift_alert(drift_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_drift_alert_on_kafka_error(self, drift_detector):
        """Testa tratamento de erro ao publicar no Kafka."""
        mock_kafka = AsyncMock()
        mock_kafka.produce_and_wait = AsyncMock(side_effect=Exception("Kafka connection error"))
        drift_detector.kafka_producer = mock_kafka

        drift_data = {
            "model_version": "v1.0.0",
            "drift_detected": True
        }

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
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.80,
                    "count": 100
                }])
            else:  # current
                mock_cursor.to_list = AsyncMock(return_value=[{
                    "_id": None,
                    "approve_rate": 0.70,
                    "avg_confidence": 0.60,  # Drift detectado
                    "count": 50
                }])
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
            mock_cursor.to_list = AsyncMock(return_value=[{
                "_id": None,
                "approve_rate": 0.70,
                "avg_confidence": 0.75,
                "count": 100
            }])
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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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
            canary_traffic_percentage=20
        )

        assert deployer.canary_duration_minutes == 120
        assert deployer.canary_traffic_percentage == 20

    def test_canary_deployer_class_has_active_canaries_dict(self):
        """Testa que a classe mantém dicionário de canaries ativos."""
        assert hasattr(CanaryDeployer, '_active_canaries')
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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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
                    "comparison": {"f1_delta": 0.05}
                }
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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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
                    "comparison": {"f1_delta": 0.05}
                }
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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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
                    "comparison": {"f1_delta": -0.05}
                }
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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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

        deployer = CanaryDeployer(
            model_repo=mock_repo,
            kafka_producer=mock_kafka
        )

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
            model_repo=mock_repo,
            kafka_producer=mock_kafka,
            canary_traffic_percentage=25
        )

        result = await deployer._calculate_traffic_split("v2.0.0", "v1.0.0")

        assert result["canary_percentage"] == 25
        assert result["baseline_percentage"] == 75
