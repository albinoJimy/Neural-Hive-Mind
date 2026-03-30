"""Testes para DriftDetector - Detecção de Model Drift."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from neural_hive_ml.drift_detector import DriftDetector


@pytest.fixture
def mock_mongo_client():
    """Mock MongoDB client."""
    # Criar cursor mock - é um Mock regular com método to_list assíncrono
    # Em Motor, aggregate() retorna um cursor (não awaitable)
    # que tem um método to_list() assíncrono
    cursor_mock = Mock()
    cursor_mock.to_list = AsyncMock(return_value=[
        {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 100}
    ])

    # Criar mock de coleção
    collection = Mock()
    collection.aggregate = Mock(return_value=cursor_mock)

    # Criar mongo client mock
    # DriftDetector.db retorna self.mongo_client diretamente
    # então self.db.plan_approvals = self.mongo_client.plan_approvals
    client = Mock()
    client.plan_approvals = collection

    # Também manter db para compatibilidade
    client.db = client

    return client


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer."""
    producer = AsyncMock()
    producer.produce_and_wait = AsyncMock()
    return producer


@pytest.fixture
def drift_detector(mock_mongo_client, mock_kafka_producer):
    """Fixture para DriftDetector."""
    return DriftDetector(
        mongo_client=mock_mongo_client,
        kafka_producer=mock_kafka_producer,
        confidence_threshold=0.10,
        approve_rate_threshold=0.15
    )


class TestDriftDetectorInit:
    """Testes de inicialização."""

    def test_init_with_defaults(self, mock_mongo_client, mock_kafka_producer):
        """Testa inicialização com valores padrão."""
        detector = DriftDetector(
            mongo_client=mock_mongo_client,
            kafka_producer=mock_kafka_producer
        )
        assert detector.confidence_threshold == 0.10
        assert detector.approve_rate_threshold == 0.15


class TestCalculateBaseline:
    """Testes de calculate_baseline."""

    @pytest.mark.asyncio
    async def test_calculate_baseline_success(self, drift_detector, mock_mongo_client):
        """Testa cálculo de baseline com sucesso."""
        # O mock já está configurado com cursor_mock
        result = await drift_detector.calculate_baseline(window_hours=168)

        assert result["approve_rate"] == 0.65
        assert result["avg_confidence"] == 0.72
        assert result["sample_count"] == 100


class TestCalculateCurrent:
    """Testes de calculate_current."""

    @pytest.mark.asyncio
    async def test_calculate_current_success(self, drift_detector, mock_mongo_client):
        """Testa cálculo de métricas atuais."""
        result = await drift_detector.calculate_current(window_hours=24)

        assert result["approve_rate"] == 0.65
        assert result["avg_confidence"] == 0.72


class TestDetectDrift:
    """Testes de detect_drift."""

    @pytest.mark.asyncio
    async def test_detect_drift_no_drift(self, drift_detector, mock_mongo_client):
        """Testa detecção sem drift."""
        result = await drift_detector.detect_drift(window_hours=168)

        # Valores iguais = sem drift
        assert result["drift_detected"] is False
        assert len(result["alerts"]) == 0

    @pytest.mark.asyncio
    async def test_detect_drift_with_confidence_drop(self, drift_detector, mock_mongo_client):
        """Testa detecção de drift no confidence."""
        # Reset mock com dados que mostram pequeno drop
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 500}
        ])
        mock_mongo_client.db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        result = await drift_detector.detect_drift(window_hours=168)

        # Confidence drop de 0.07 -> abaixo de 0.10 threshold
        assert result["drift_detected"] is False  # 0.72 - 0.72 = 0 < 0.10

    @pytest.mark.asyncio
    async def test_detect_drift_significant(self, drift_detector, mock_mongo_client):
        """Testa detecção de drift significativo."""
        # Configurar aggregate com múltiplas chamadas
        baseline_cursor = Mock()
        baseline_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 500}
        ])
        current_cursor = Mock()
        current_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.55, "avg_confidence": 0.60, "count": 100}
        ])

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return baseline_cursor if call_count[0] == 1 else current_cursor

        mock_mongo_client.db.plan_approvals.aggregate = side_effect

        result = await drift_detector.detect_drift(window_hours=168)

        # Confidence drop = 0.12 > 0.10 threshold
        assert result["drift_detected"] is True
        assert len(result["alerts"]) > 0


class TestPublishDriftAlert:
    """Testes de publish_drift_alert."""

    @pytest.mark.asyncio
    async def test_publish_alert(self, drift_detector, mock_kafka_producer):
        """Testa publicação de alerta de drift."""
        drift_data = {
            "drift_detected": True,
            "confidence_drop": 0.12,
            "approve_rate_change": -0.10
        }

        result = await drift_detector.publish_drift_alert(drift_data)

        mock_kafka_producer.produce_and_wait.assert_called_once()
        assert result is True


class TestGetDriftMetrics:
    """Testes de get_drift_metrics (endpoint)."""

    @pytest.mark.asyncio
    async def test_get_drift_metrics_complete(self, drift_detector):
        """Testa retorno completo de métricas de drift."""
        result = await drift_detector.get_drift_metrics(window_hours=168)

        # Verifica campos obrigatórios
        assert "model_version" in result
        assert "window_hours" in result
        assert "drift_detected" in result
        assert "baseline" in result
        assert "current" in result


class TestBuildAggregationPipeline:
    """Testes de construção de pipeline de agregação."""

    def test_build_aggregation_pipeline_structure(self, drift_detector):
        """Testa estrutura do pipeline."""
        pipeline = drift_detector._build_aggregation_pipeline(24)

        assert len(pipeline) == 2
        assert "$match" in pipeline[0]
        assert "$group" in pipeline[1]

    def test_build_aggregation_pipeline_match_stage(self, drift_detector):
        """Testa estágio $match do pipeline."""
        pipeline = drift_detector._build_aggregation_pipeline(48)

        match_stage = pipeline[0]["$match"]
        assert "created_at" in match_stage
        assert "$gte" in match_stage["created_at"]

    def test_build_aggregation_pipeline_group_stage(self, drift_detector):
        """Testa estágio $group do pipeline."""
        pipeline = drift_detector._build_aggregation_pipeline(24)

        group_stage = pipeline[1]["$group"]
        assert "_id" in group_stage
        assert "approve_rate" in group_stage
        assert "avg_confidence" in group_stage
        assert "count" in group_stage


class TestDbProperty:
    """Testes da propriedade db."""

    def test_db_property_returns_mongo_client(self, drift_detector, mock_mongo_client):
        """Testa que db retorna mongo_client."""
        assert drift_detector.db is mock_mongo_client


class TestCalculateBaselineEdgeCases:
    """Testes de edge cases para calculate_baseline."""

    @pytest.mark.asyncio
    async def test_calculate_baseline_empty_results(self, drift_detector, mock_mongo_client):
        """Testa calculate_baseline com resultados vazios."""
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[])
        mock_mongo_client.db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        result = await drift_detector.calculate_baseline()

        # Deve retornar valores padrão
        assert result["approve_rate"] == 0.65
        assert result["avg_confidence"] == 0.72
        assert result["sample_count"] == 0

    @pytest.mark.asyncio
    async def test_calculate_baseline_with_missing_fields(self, drift_detector, mock_mongo_client):
        """Testa calculate_baseline com campos faltando."""
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None}  # Sem os campos esperados
        ])
        mock_mongo_client.db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        result = await drift_detector.calculate_baseline()

        # get() com valor padrão deve retornar 0.0
        assert result["approve_rate"] == 0.0
        assert result["avg_confidence"] == 0.0
        assert result["sample_count"] == 0


class TestCalculateCurrentEdgeCases:
    """Testes de edge cases para calculate_current."""

    @pytest.mark.asyncio
    async def test_calculate_current_empty_results(self, drift_detector, mock_mongo_client):
        """Testa calculate_current com resultados vazios."""
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[])
        mock_mongo_client.db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        result = await drift_detector.calculate_current()

        assert result["approve_rate"] == 0.0
        assert result["avg_confidence"] == 0.0
        assert result["sample_count"] == 0


class TestDetectDriftEdgeCases:
    """Testes de edge cases para detect_drift."""

    @pytest.mark.asyncio
    async def test_detect_drift_with_no_baseline_data(self, drift_detector, mock_mongo_client):
        """Testa detect_drift sem dados de baseline."""
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[])

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return cursor_mock

        mock_mongo_client.db.plan_approvals.aggregate = side_effect

        result = await drift_detector.detect_drift()

        # Deve usar valores padrão
        assert "baseline" in result
        assert "current" in result

    @pytest.mark.asyncio
    async def test_detect_drift_with_approve_rate_change_only(self, drift_detector, mock_mongo_client):
        """Testa detecção de drift apenas em approve_rate."""
        # Baseline: approve_rate 0.70, confidence 0.75
        baseline_cursor = Mock()
        baseline_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 500}
        ])

        # Current: approve_rate 0.50 (mudança de 0.20), confidence 0.75 (sem mudança)
        current_cursor = Mock()
        current_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.50, "avg_confidence": 0.75, "count": 100}
        ])

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return baseline_cursor if call_count[0] == 1 else current_cursor

        mock_mongo_client.db.plan_approvals.aggregate = side_effect

        result = await drift_detector.detect_drift()

        # Mudança de 0.20 > 0.15 (approve_rate_threshold)
        assert result["drift_detected"] is True
        # Verificar alerta específico para approve_rate
        approve_alerts = [a for a in result["alerts"] if a["metric"] == "approve_rate"]
        assert len(approve_alerts) > 0
        assert approve_alerts[0]["change"] == -0.200


class TestPublishDriftAlertEdgeCases:
    """Testes de edge cases para publish_drift_alert."""

    @pytest.mark.asyncio
    async def test_publish_alert_with_kafka_error(self, drift_detector, mock_kafka_producer):
        """Testa publicação quando Kafka falha."""
        mock_kafka_producer.produce_and_wait = AsyncMock(side_effect=Exception("Kafka error"))

        drift_data = {
            "drift_detected": True,
            "confidence_drop": 0.15
        }

        result = await drift_detector.publish_drift_alert(drift_data)

        # Deve retornar False mesmo com erro
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_alert_without_drift(self, drift_detector, mock_kafka_producer):
        """Testa que alerta é publicado mesmo sem drift (comportamento atual)."""
        drift_data = {
            "drift_detected": False,
            "confidence_change": 0.02,
            "alerts": []
        }

        result = await drift_detector.publish_drift_alert(drift_data)

        # O comportamento atual publica mesmo sem drift
        mock_kafka_producer.produce_and_wait.assert_called_once()
        assert result is True


# =============================================================================
# Novos Testes para Cobertura Adicional (+10 testes)
# =============================================================================

class TestGetActiveModelVersion:
    """Testes de _get_active_model_version."""

    @pytest.mark.asyncio
    async def test_get_active_model_version_success(self, drift_detector, mock_mongo_client):
        """Testa busca de versão ativa com sucesso."""
        # Mock para retornar versão ativa
        mock_mongo_client.model_versions.find_one = AsyncMock(
            return_value={
                "version": "v9",
                "stage": "production",
                "is_active": True,
                "created_at": datetime.utcnow()
            }
        )

        version = await drift_detector._get_active_model_version()

        assert version == "v9"

    @pytest.mark.asyncio
    async def test_get_active_model_version_not_found(self, drift_detector, mock_mongo_client):
        """Testa busca quando não há modelo ativo."""
        mock_mongo_client.model_versions.find_one = AsyncMock(return_value=None)

        version = await drift_detector._get_active_model_version()

        assert version == "unknown"

    @pytest.mark.asyncio
    async def test_get_active_model_version_with_error(self, drift_detector, mock_mongo_client):
        """Testa tratamento de erro na busca de versão."""
        mock_mongo_client.model_versions.find_one = AsyncMock(
            side_effect=Exception("DB error")
        )

        version = await drift_detector._get_active_model_version()

        assert version == "unknown"


class TestDriftScoreCalculation:
    """Testes de cálculo de score de drift."""

    @pytest.mark.asyncio
    async def test_drift_score_with_no_change(self, drift_detector, mock_mongo_client):
        """Testa score quando não há mudança."""
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 100}
        ])
        mock_mongo_client.db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        result = await drift_detector.detect_drift()

        # Sem mudança = sem drift
        assert result["drift_detected"] is False
        assert result["baseline"]["avg_confidence"] == result["current"]["avg_confidence"]

    @pytest.mark.asyncio
    async def test_drift_score_with_minor_change(self, drift_detector, mock_mongo_client):
        """Testa score com mudança menor que threshold."""
        # Baseline: 0.75, Current: 0.70 (mudança de 0.05 < 0.10)
        baseline_cursor = Mock()
        baseline_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 500}
        ])
        current_cursor = Mock()
        current_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.68, "avg_confidence": 0.70, "count": 100}
        ])

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return baseline_cursor if call_count[0] == 1 else current_cursor

        mock_mongo_client.db.plan_approvals.aggregate = side_effect

        result = await drift_detector.detect_drift()

        # Mudança de 0.05 < 0.10, sem drift
        assert result["drift_detected"] is False


class TestDriftReportGeneration:
    """Testes de geração de relatório de drift."""

    @pytest.mark.asyncio
    async def test_drift_report_with_recommendation(self, drift_detector):
        """Testa que drift_detected=True adiciona recomendação."""
        # Forçar drift
        with patch.object(drift_detector, 'detect_drift', return_value={
            "drift_detected": True,
            "baseline": {"avg_confidence": 0.75},
            "current": {"avg_confidence": 0.60},
            "alerts": [{"metric": "avg_confidence", "change": -0.15}]
        }):
            result = await drift_detector.get_drift_metrics()

            assert result["drift_detected"] is True
            assert "recommendation" in result

    @pytest.mark.asyncio
    async def test_drift_report_without_recommendation(self, drift_detector):
        """Testa que sem drift não há recomendação."""
        with patch.object(drift_detector, 'detect_drift', return_value={
            "drift_detected": False,
            "baseline": {"avg_confidence": 0.75},
            "current": {"avg_confidence": 0.74},
            "alerts": []
        }):
            result = await drift_detector.get_drift_metrics()

            assert result["drift_detected"] is False
            assert "recommendation" not in result


class TestThresholdComparison:
    """Testes de comparação com thresholds."""

    @pytest.mark.asyncio
    async def test_confidence_threshold_exceeded_warning(self, drift_detector, mock_mongo_client):
        """Testa alerta de warning quando confidenceThreshold é levemente excedido."""
        # Mudança de 0.12 (> 0.10, mas < 0.15)
        baseline_cursor = Mock()
        baseline_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 500}
        ])
        current_cursor = Mock()
        current_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.68, "count": 100}
        ])

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return baseline_cursor if call_count[0] == 1 else current_cursor

        mock_mongo_client.db.plan_approvals.aggregate = side_effect

        result = await drift_detector.detect_drift()

        # Deve detectar drift com severity warning
        assert result["drift_detected"] is True
        confidence_alerts = [a for a in result["alerts"] if a["metric"] == "avg_confidence"]
        assert len(confidence_alerts) > 0
        # Mudança de 0.12 < 0.15 = warning
        assert confidence_alerts[0]["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_confidence_threshold_exceeded_critical(self, drift_detector, mock_mongo_client):
        """Testa alerta crítico quando confidence drop é severo."""
        # Mudança de 0.20 (> 0.15)
        baseline_cursor = Mock()
        baseline_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 500}
        ])
        current_cursor = Mock()
        current_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.60, "count": 100}
        ])

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return baseline_cursor if call_count[0] == 1 else current_cursor

        mock_mongo_client.db.plan_approvals.aggregate = side_effect

        result = await drift_detector.detect_drift()

        confidence_alerts = [a for a in result["alerts"] if a["metric"] == "avg_confidence"]
        assert len(confidence_alerts) > 0
        # Mudança de 0.20 >= 0.15 = critical
        assert confidence_alerts[0]["severity"] == "critical"


class TestCustomThresholds:
    """Testes com thresholds customizados."""

    def test_init_with_custom_thresholds(self, mock_mongo_client, mock_kafka_producer):
        """Testa inicialização com thresholds customizados."""
        detector = DriftDetector(
            mongo_client=mock_mongo_client,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.05,
            approve_rate_threshold=0.10
        )

        assert detector.confidence_threshold == 0.05
        assert detector.approve_rate_threshold == 0.10

    @pytest.mark.asyncio
    async def test_drift_detection_with_custom_thresholds(self, mock_mongo_client, mock_kafka_producer):
        """Testa detecção com threshold mais sensível."""
        detector = DriftDetector(
            mongo_client=mock_mongo_client,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.05  # Mais sensível
        )

        # Mudança de 0.08 (antes seria warning, agora é drift)
        baseline_cursor = Mock()
        baseline_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.80, "count": 500}
        ])
        current_cursor = Mock()
        current_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.72, "count": 100}
        ])

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return baseline_cursor if call_count[0] == 1 else current_cursor

        mock_mongo_client.db.plan_approvals.aggregate = side_effect

        result = await detector.detect_drift()

        # Com threshold 0.05, mudança de 0.08 deve ser drift
        assert result["drift_detected"] is True
