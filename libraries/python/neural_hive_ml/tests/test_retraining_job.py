"""Testes para RetrainingJob - Auto-Retraining Pipeline."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from neural_hive_ml.retraining_job import RetrainingJob


@pytest.fixture
def mock_mlflow_client():
    """Mock MLflowClient."""
    client = MagicMock()
    client.log_model = MagicMock(return_value="v9")
    client.promote_model = MagicMock()
    return client


@pytest.fixture
def mock_model_repo():
    """Mock ModelVersionRepository."""
    repo = AsyncMock()
    repo.get_active_model = AsyncMock(return_value={
        "version": "v8",
        "f1_score": 0.73,
        "accuracy": 0.80
    })
    repo.create = AsyncMock()
    repo.promote_model = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer."""
    producer = AsyncMock()
    producer.produce_and_wait = AsyncMock()
    return producer


@pytest.fixture
def retraining_job(mock_mlflow_client, mock_model_repo, mock_kafka_producer):
    """Fixture para RetrainingJob."""
    return RetrainingJob(
        mlflow_client=mock_mlflow_client,
        model_repo=mock_model_repo,
        kafka_producer=mock_kafka_producer
    )


class TestRetrainingJobInit:
    """Testes de inicialização."""

    def test_init_with_defaults(self, mock_mlflow_client, mock_model_repo, mock_kafka_producer):
        """Testa inicialização com valores padrão."""
        job = RetrainingJob(
            mlflow_client=mock_mlflow_client,
            model_repo=mock_model_repo,
            kafka_producer=mock_kafka_producer
        )
        assert job.retrain_threshold == 100
        assert job.min_f1_improvement == 0.05

    def test_init_with_custom_thresholds(self, mock_mlflow_client, mock_model_repo, mock_kafka_producer):
        """Testa inicialização com thresholds customizados."""
        job = RetrainingJob(
            mlflow_client=mock_mlflow_client,
            model_repo=mock_model_repo,
            kafka_producer=mock_kafka_producer,
            retrain_threshold=200,
            min_f1_improvement=0.10
        )
        assert job.retrain_threshold == 200
        assert job.min_f1_improvement == 0.10


class TestCheckThreshold:
    """Testes de check_threshold."""

    async def test_threshold_met(self, retraining_job, mock_model_repo):
        """Testa que threshold é atingido."""
        mock_model_repo.count_pending_samples = AsyncMock(return_value=150)

        result = await retraining_job.check_threshold()

        assert result["has_enough_samples"] is True
        assert result["sample_count"] == 150

    async def test_threshold_not_met(self, retraining_job, mock_model_repo):
        """Testa que threshold não é atingido."""
        mock_model_repo.count_pending_samples = AsyncMock(return_value=50)

        result = await retraining_job.check_threshold()

        assert result["has_enough_samples"] is False
        assert result["sample_count"] == 50


class TestExecuteRetraining:
    """Testes de execute_retraining."""

    @patch('neural_hive_ml.retraining_job.subprocess.run')
    async def test_execute_retraining_success(self, mock_run, retraining_job):
        """Testa execução de retreino com sucesso."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="F1-Score: 0.75\nAccuracy: 0.82\nVersion: v9",
            stderr=""
        )

        result = await retraining_job.execute_retraining()

        assert result["success"] is True
        # Versão extraída do parse ou fallback
        assert result["job_id"] is not None

    @patch('neural_hive_ml.retraining_job.subprocess.run')
    async def test_execute_retraining_failure(self, mock_run, retraining_job):
        """Testa execução de retreino com falha."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Training failed"
        )

        result = await retraining_job.execute_retraining()

        assert result["success"] is False
        assert "error" in result


class TestValidateModel:
    """Testes de validate_model."""

    async def test_validate_model_improves(self, retraining_job, mock_model_repo):
        """Testa que modelo melhora o suficiente."""
        mock_model_repo.get_active_model = AsyncMock(return_value={
            "version": "v8",
            "f1_score": 0.73
        })

        new_metrics = {
            "f1_score": 0.79,
            "accuracy": 0.84
        }

        result = await retraining_job.validate_model(new_metrics)

        assert result["should_deploy"] is True
        assert abs(result["f1_improvement"] - 0.06) < 0.001

    async def test_validate_model_no_improvement(self, retraining_job, mock_model_repo):
        """Testa que modelo não melhora o suficiente."""
        mock_model_repo.get_active_model = AsyncMock(return_value={
            "version": "v8",
            "f1_score": 0.73
        })

        new_metrics = {
            "f1_score": 0.74,
            "accuracy": 0.81
        }

        result = await retraining_job.validate_model(new_metrics)

        assert result["should_deploy"] is False

    async def test_validate_model_no_baseline(self, retraining_job, mock_model_repo):
        """Testa quando não há baseline (primeiro modelo)."""
        mock_model_repo.get_active_model = AsyncMock(return_value=None)

        new_metrics = {
            "f1_score": 0.70,
            "accuracy": 0.80
        }

        result = await retraining_job.validate_model(new_metrics)

        assert result["should_deploy"] is True


class TestRegisterToMLflow:
    """Testes de register_to_mlflow."""

    async def test_register_to_mlflow_success(self, retraining_job, mock_mlflow_client):
        """Testa registro no MLflow."""
        mock_model = MagicMock()

        result = await retraining_job.register_to_mlflow(
            model=mock_model,
            version="v9",
            metrics={"f1_score": 0.75},
            params={"n_estimators": 100}
        )

        mock_mlflow_client.log_model.assert_called_once()
        assert result["version"] == "v9"


class TestPublishKafkaEvent:
    """Testes de publish_kafka_event."""

    async def test_publish_trained_event(self, retraining_job, mock_kafka_producer):
        """Testa publicação de evento modelo treinado."""
        result = await retraining_job.publish_kafka_event(
            event_type="model_trained",
            version="v9",
            f1_score=0.75
        )

        mock_kafka_producer.produce_and_wait.assert_called_once()
        assert result is True


class TestRunRetraining:
    """Testes de run_retraining (end-to-end)."""

    @patch('neural_hive_ml.retraining_job.subprocess.run')
    async def test_run_retraining_success(self, mock_run, retraining_job, mock_model_repo, mock_mlflow_client):
        """Testa fluxo completo de retreino com sucesso."""
        # Setup mocks
        mock_model_repo.count_pending_samples = AsyncMock(return_value=150)
        mock_model_repo.get_active_model = AsyncMock(return_value={
            "version": "v8",
            "f1_score": 0.70
        })
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="F1-Score: 0.78\nAccuracy: 0.85"
        )
        mock_model = MagicMock()

        result = await retraining_job.run_retraining(model=mock_model)

        assert result["success"] is True
        assert result["deployed"] is True


class TestGetJobStatus:
    """Testes de get_job_status."""

    async def test_get_job_status_completed(self, retraining_job):
        """Testa status de job completado."""
        retraining_job._job_status = {
            "job_id": "retrain-123",
            "status": "completed",
            "started_at": datetime.now() - timedelta(hours=1),
            "completed_at": datetime.now()
        }

        result = await retraining_job.get_job_status("retrain-123")

        assert result["status"] == "completed"

    async def test_get_job_status_not_found(self, retraining_job):
        """Testa status de job não encontrado."""
        result = await retraining_job.get_job_status("nonexistent")

        assert result is None
