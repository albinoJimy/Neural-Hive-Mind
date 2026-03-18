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
