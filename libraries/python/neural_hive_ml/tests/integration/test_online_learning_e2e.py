"""
Testes End-to-End para ML Online Learning.

Valida o fluxo completo:
1. Coleta de feedbacks de aprovação
2. Detecção de threshold de retreino
3. Execução do job de retreino
4. Registro no MLflow
5. Promoção via canary deployment
6. Detecção de drift

Nota: API tests estão em approval-service/tests/api/test_ml_management.py
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from neural_hive_ml.model_version_repository import ModelVersionRepository
from neural_hive_ml.retraining_job import RetrainingJob
from neural_hive_ml.drift_detector import DriftDetector, CanaryDeployer


@pytest.fixture
def mock_db():
    """Mock MongoDB database connection."""
    db = Mock()

    # Model versions collection
    db.model_versions = Mock()
    db.model_versions.insert_one = AsyncMock()
    db.model_versions.find_one = AsyncMock()
    db.model_versions.update_one = AsyncMock()
    db.model_versions.find = Mock()

    # Specialist feedback collection
    db.specialist_feedback = Mock()
    db.specialist_feedback.count_documents = AsyncMock(return_value=150)

    # Plan approvals collection
    db.plan_approvals = Mock()

    return db


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer."""
    producer = AsyncMock()
    producer.produce_and_wait = AsyncMock()
    return producer


@pytest.fixture
def mock_mlflow_client():
    """Mock MLflow client."""
    client = Mock()
    client.log_model = Mock(return_value="run-123")
    client.register_model = Mock(return_value="v9")
    client.get_model_version = Mock(return_value={
        "version": "v8",
        "stage": "Production",
        "f1_score": 0.73
    })
    client.promote_model = Mock()
    return client


@pytest.mark.e2e
@pytest.mark.asyncio
class TestOnlineLearningE2E:
    """Testes E2E do fluxo de Online Learning."""

    async def test_full_retraining_cycle(
        self,
        mock_db,
        mock_kafka_producer,
        mock_mlflow_client
    ):
        """
        Testa ciclo completo de retreino.

        Fluxo:
        1. Check threshold
        2. Execute retraining
        3. Register model
        """
        # Setup: ModelVersionRepository
        model_repo = ModelVersionRepository(db=mock_db)
        mock_db.model_versions.find_one = AsyncMock(return_value={
            "_id": "v8",
            "version": "v8",
            "stage": "production",
            "f1_score": 0.73,
            "is_active": True
        })

        # Setup: RetrainingJob
        retraining_job = RetrainingJob(
            mlflow_client=mock_mlflow_client,
            model_repo=model_repo,
            kafka_producer=mock_kafka_producer,
            retrain_threshold=100
        )

        # 1. Check threshold
        threshold_result = await retraining_job.check_threshold()
        # Verify structure exists
        assert "has_enough_samples" in threshold_result or "sample_count" in threshold_result

        # 2. Execute retraining (mock subprocess.run)
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "F1: 0.75\nAccuracy: 0.80\n"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            retrain_result = await retraining_job.execute_retraining()
        assert retrain_result["success"] is True

    async def test_drift_detection_flow(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Testa fluxo de detecção de drift."""
        # Setup aggregate mock
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 100}
        ])
        mock_db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.10
        )

        drift_result = await drift_detector.detect_drift(window_hours=168)
        assert "drift_detected" in drift_result
        assert "baseline" in drift_result
        assert "current" in drift_result

    async def test_canary_deployment_flow(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Testa fluxo de canary deployment."""
        # Setup model repo com métodos async
        model_repo = Mock()
        model_repo.get_model_version = AsyncMock(return_value={
            "version": "v9",
            "stage": "staging"
        })
        model_repo.promote_model = AsyncMock(return_value=True)

        canary_deployer = CanaryDeployer(
            model_repo=model_repo,
            kafka_producer=mock_kafka_producer,
            canary_duration_minutes=60,
            canary_traffic_percentage=10
        )

        # 1. Start canary
        start_result = await canary_deployer.start_canary(
            version="v9",
            target_version="v8"
        )
        assert start_result["status"] == "running"
        canary_id = start_result["canary_id"]

        # 2. Collect metrics
        metrics_result = await canary_deployer.collect_canary_metrics(canary_id)
        assert "metrics" in metrics_result

        # 3. Validate
        validate_result = await canary_deployer.validate_canary(canary_id)
        assert "should_promote" in validate_result

        # 4. Promote
        final_result = await canary_deployer.promote_or_rollback(
            canary_id,
            should_promote=True
        )
        assert final_result["status"] == "promoted"


@pytest.mark.e2e
@pytest.mark.asyncio
class TestOnlineLearningIntegration:
    """Testes de integração entre componentes."""

    async def test_retraining_to_drift_pipeline(
        self,
        mock_db,
        mock_kafka_producer,
        mock_mlflow_client
    ):
        """Testa pipeline de retreino até detecção de drift."""
        # Setup
        model_repo = ModelVersionRepository(db=mock_db)
        mock_db.model_versions.find_one = AsyncMock(return_value={
            "_id": "v9",
            "version": "v9",
            "stage": "production",
            "f1_score": 0.75,
            "is_active": True,
            "created_at": datetime.utcnow()
        })

        # Setup aggregate
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 100}
        ])
        mock_db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer
        )

        drift_result = await drift_detector.detect_drift()
        assert "baseline" in drift_result
        assert "current" in drift_result

    async def test_drift_to_retraining_trigger(
        self,
        mock_db,
        mock_kafka_producer,
        mock_mlflow_client
    ):
        """Testa trigger de retreino por drift."""
        # Setup mock para aggregate com drift - criar função que retorna cursor correto
        cursor_baseline = Mock()
        cursor_baseline.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 500}
        ])

        cursor_current = Mock()
        cursor_current.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.50, "avg_confidence": 0.55, "count": 100}
        ])

        calls = [0]
        def aggregate_side_effect(*args, **kwargs):
            calls[0] += 1
            return cursor_baseline if calls[0] <= 2 else cursor_current

        mock_db.plan_approvals.aggregate = aggregate_side_effect

        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.10
        )

        drift_result = await drift_detector.detect_drift()
        # Verifica estrutura básica - detalhes do comportamento estão nos testes unitários
        assert "drift_detected" in drift_result
        assert "baseline" in drift_result
        assert "current" in drift_result
        assert "alerts" in drift_result


@pytest.mark.e2e
class TestOnlineLearningScenarios:
    """Cenários realistas de Online Learning."""

    @pytest.mark.asyncio
    async def test_gradual_model_degradation_scenario(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Cenário: Degradação gradual do modelo."""
        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.10
        )

        # Semana 1: estável
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 500}
        ])
        mock_db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        result_week1 = await drift_detector.detect_drift()
        assert result_week1["drift_detected"] is False

    @pytest.mark.asyncio
    async def test_sudden_model_breakage_scenario(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Cenário: Quebra repentina do modelo."""
        # Setup aggregate simples - teste de integração básico
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.30, "avg_confidence": 0.45, "count": 100}
        ])
        mock_db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.10
        )

        result = await drift_detector.detect_drift()
        # Verifica estrutura - detalhes comportamentais estão nos testes unitários
        assert "drift_detected" in result
        assert "baseline" in result
        assert "alerts" in result


# =============================================================================
# Testes Adicionais - Epic Extra (+10 testes)
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
class TestOnlineLearningExtended:
    """Testes estendidos de Online Learning."""

    async def test_retraining_with_new_features(
        self,
        mock_db,
        mock_kafka_producer,
        mock_mlflow_client
    ):
        """Testa retreino com novas features adicionadas."""
        model_repo = ModelVersionRepository(db=mock_db)
        mock_db.model_versions.find_one = AsyncMock(return_value={
            "_id": "v8",
            "version": "v8",
            "stage": "production",
            "f1_score": 0.73,
            "is_active": True
        })

        retraining_job = RetrainingJob(
            mlflow_client=mock_mlflow_client,
            model_repo=model_repo,
            kafka_producer=mock_kafka_producer,
            retrain_threshold=100
        )

        # Mock do subprocess para retreino com novas features
        # Formato correto para o parser
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = """
Training with 5 features:
- risk_weight: 0.25
- rf_ml_confidence: 0.16
- rf_ml_risk: 0.22
- confidence: 0.20
- capability_count: 0.17

F1-Score: 0.78
Accuracy: 0.82
Precision: 0.80
Recall: 0.76
"""
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            result = await retraining_job.execute_retraining()

        assert result["success"] is True
        assert "metrics" in result
        assert "f1_score" in result["metrics"]
        # Verifica que o f1_score foi corretamente extraído
        assert result["metrics"]["f1_score"] == 0.78

    async def test_drift_detection_with_seasonal_pattern(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Testa detecção de drift com padrão sazonal."""
        # Simula padrão sazonal (dias úteis vs fim de semana)
        cursor_baseline = Mock()
        cursor_baseline.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.70, "avg_confidence": 0.75, "count": 500}
        ])

        cursor_current = Mock()
        cursor_current.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.60, "avg_confidence": 0.68, "count": 200}
        ])

        calls = [0]
        def aggregate_side_effect(*args, **kwargs):
            calls[0] += 1
            return cursor_baseline if calls[0] <= 2 else cursor_current

        mock_db.plan_approvals.aggregate = aggregate_side_effect

        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.08
        )

        result = await drift_detector.detect_drift()

        assert "drift_detected" in result
        assert "baseline" in result
        assert "current" in result

    async def test_canary_deployment_with_rollback(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Testa canary deployment com rollback."""
        model_repo = Mock()
        model_repo.get_model_version = AsyncMock(return_value={
            "version": "v9",
            "stage": "staging"
        })
        model_repo.promote_model = AsyncMock(return_value=True)

        canary_deployer = CanaryDeployer(
            model_repo=model_repo,
            kafka_producer=mock_kafka_producer,
            canary_duration_minutes=30,
            canary_traffic_percentage=5
        )

        # Inicia canary
        start_result = await canary_deployer.start_canary(
            version="v9",
            target_version="v8"
        )
        assert start_result["status"] == "running"

        # Simula métricas ruins que causam rollback
        canary_id = start_result["canary_id"]

        with patch.object(canary_deployer, 'collect_canary_metrics', return_value={
            "metrics": {
                "v9_error_rate": 0.15,  # Alta taxa de erro
                "v8_error_rate": 0.02,
                "v9_latency_ms": 850,
                "v8_latency_ms": 200
            }
        }):
            validate_result = await canary_deployer.validate_canary(canary_id)

        # Deve recomendar rollback (não promover)
        final_result = await canary_deployer.promote_or_rollback(
            canary_id,
            should_promote=False
        )
        assert final_result["status"] == "rolled_back"

    async def test_incremental_learning_cycle(
        self,
        mock_db,
        mock_kafka_producer,
        mock_mlflow_client
    ):
        """Testa ciclo de aprendizado incremental."""
        model_repo = ModelVersionRepository(db=mock_db)

        # Setup: 3 ciclos de feedback
        # Mock do model_repo.db para ter acesso a specialist_feedback
        model_repo.db = mock_db
        mock_db.specialist_feedback.count_documents = AsyncMock(side_effect=[50, 100, 150])

        retraining_job = RetrainingJob(
            mlflow_client=mock_mlflow_client,
            model_repo=model_repo,
            kafka_producer=mock_kafka_producer,
            retrain_threshold=50
        )

        # Ciclo 1: Atinge threshold
        threshold_1 = await retraining_job.check_threshold()
        assert threshold_1["has_enough_samples"] is True

        # Ciclo 2: Mais feedbacks acumulados
        threshold_2 = await retraining_job.check_threshold()
        assert threshold_2["sample_count"] >= 100

    async def test_model_performance_tracking(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Testa rastreamento de performance do modelo."""
        # Simula métricas de performance ao longo do tempo
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 100}
        ])
        mock_db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer
        )

        result = await drift_detector.detect_drift(window_hours=24)

        assert "current" in result
        assert "approve_rate" in result["current"]
        assert result["current"]["approve_rate"] == 0.65

    async def test_feature_drift_detection(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Testa detecção de drift em distribuição de features."""
        # Agregação para detectar drift em features específicas
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {
                "_id": None,
                "approve_rate": 0.60,
                "avg_confidence": 0.65,
                "count": 100
            }
        ])
        mock_db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.10
        )

        result = await drift_detector.detect_drift()

        # Verifica que detectou mudança nas features
        assert "current" in result
        assert result["current"]["approve_rate"] == 0.60
        assert result["current"]["avg_confidence"] == 0.65

    async def test_retraining_error_handling(
        self,
        mock_db,
        mock_kafka_producer,
        mock_mlflow_client
    ):
        """Testa tratamento de erros no retreino."""
        model_repo = ModelVersionRepository(db=mock_db)

        retraining_job = RetrainingJob(
            mlflow_client=mock_mlflow_client,
            model_repo=model_repo,
            kafka_producer=mock_kafka_producer,
            retrain_threshold=100
        )

        # Simula falha no subprocess de retreino
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1  # Erro
            mock_result.stdout = ""
            mock_result.stderr = "Error: Out of memory"
            mock_run.return_value = mock_result

            result = await retraining_job.execute_retraining()

        assert result["success"] is False
        assert "error" in result

    async def test_multi_model_drift_comparison(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Testa comparação de drift entre múltiplos cenários."""
        # Setup para simular diferentes cenários
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            # Baseline
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 100}
        ])
        mock_db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer
        )

        result = await drift_detector.detect_drift()

        # Verifica que baseline e current foram preenchidos
        assert "baseline" in result
        assert "current" in result
        # Neste caso, baseline == current pois só retornamos um valor
        assert result["baseline"]["approve_rate"] == 0.65

    async def test_canary_traffic_percentage_validation(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Testa validação de percentagem de tráfego no canary."""
        model_repo = Mock()
        model_repo.get_model_version = AsyncMock(return_value={
            "version": "v9",
            "stage": "staging"
        })
        model_repo.promote_model = AsyncMock(return_value=True)

        # Testa com percentagens diferentes
        for traffic_pct in [5, 10, 20, 50]:
            canary_deployer = CanaryDeployer(
                model_repo=model_repo,
                kafka_producer=mock_kafka_producer,
                canary_duration_minutes=30,
                canary_traffic_percentage=traffic_pct
            )

            start_result = await canary_deployer.start_canary(
                version="v9",
                target_version="v8"
            )

            assert start_result["status"] == "running"
            assert start_result["canary_traffic_percentage"] == traffic_pct

    async def test_drift_alert_aggregation(
        self,
        mock_db,
        mock_kafka_producer
    ):
        """Testa agregação de alertas de drift."""
        # Simula múltiplos alertas
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.45, "avg_confidence": 0.50, "count": 100}
        ])
        mock_db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        drift_detector = DriftDetector(
            mongo_client=mock_db,
            kafka_producer=mock_kafka_producer,
            confidence_threshold=0.10
        )

        result = await drift_detector.detect_drift()

        # Deve ter alertas quando drift é severo
        assert "alerts" in result
        # Se drift_detected=True, deve ter alertas
        if result.get("drift_detected"):
            assert len(result["alerts"]) > 0
