"""Testes para RetrainingJob - Auto-Retraining Pipeline."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neural_hive_ml.retraining_job import RetrainingJob


@pytest.fixture()
def mock_mlflow_client():
    """Mock MLflowClient."""
    client = MagicMock()
    client.log_model = MagicMock(return_value="v9")
    client.promote_model = MagicMock()
    return client


@pytest.fixture()
def mock_model_repo():
    """Mock ModelVersionRepository."""
    # Criar mock de banco de dados
    mock_db = AsyncMock()

    repo = AsyncMock()
    repo.get_active_model = AsyncMock(
        return_value={"version": "v8", "f1_score": 0.73, "accuracy": 0.80}
    )
    repo.create = AsyncMock()
    repo.promote_model = AsyncMock(return_value=True)
    repo.db = mock_db  # Adicionar db attribute
    return repo


@pytest.fixture()
def mock_kafka_producer():
    """Mock Kafka producer."""
    producer = AsyncMock()
    producer.produce_and_wait = AsyncMock()
    return producer


@pytest.fixture()
def retraining_job(mock_mlflow_client, mock_model_repo, mock_kafka_producer):
    """Fixture para RetrainingJob."""
    return RetrainingJob(
        mlflow_client=mock_mlflow_client,
        model_repo=mock_model_repo,
        kafka_producer=mock_kafka_producer,
    )


class TestRetrainingJobInit:
    """Testes de inicialização."""

    def test_init_with_defaults(self, mock_mlflow_client, mock_model_repo, mock_kafka_producer):
        """Testa inicialização com valores padrão."""
        job = RetrainingJob(
            mlflow_client=mock_mlflow_client,
            model_repo=mock_model_repo,
            kafka_producer=mock_kafka_producer,
        )
        assert job.retrain_threshold == 100
        assert job.min_f1_improvement == 0.05

    def test_init_with_custom_thresholds(
        self, mock_mlflow_client, mock_model_repo, mock_kafka_producer
    ):
        """Testa inicialização com thresholds customizados."""
        job = RetrainingJob(
            mlflow_client=mock_mlflow_client,
            model_repo=mock_model_repo,
            kafka_producer=mock_kafka_producer,
            retrain_threshold=200,
            min_f1_improvement=0.10,
        )
        assert job.retrain_threshold == 200
        assert job.min_f1_improvement == 0.10


class TestCheckThreshold:
    """Testes de check_threshold."""

    async def test_threshold_met(self, retraining_job, mock_model_repo):
        """Testa que threshold é atingido."""
        # Mock do banco de dados para retornar 150 samples
        mock_model_repo.db.specialist_feedback.count_documents = AsyncMock(return_value=150)

        result = await retraining_job.check_threshold()

        assert result["has_enough_samples"] is True
        assert result["sample_count"] == 150

    async def test_threshold_not_met(self, retraining_job, mock_model_repo):
        """Testa que threshold não é atingido."""
        mock_model_repo.db.specialist_feedback.count_documents = AsyncMock(return_value=50)

        result = await retraining_job.check_threshold()

        assert result["has_enough_samples"] is False
        assert result["sample_count"] == 50


class TestExecuteRetraining:
    """Testes de execute_retraining."""

    @patch("neural_hive_ml.retraining_job.subprocess.run")
    async def test_execute_retraining_success(self, mock_run, retraining_job):
        """Testa execução de retreino com sucesso."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="F1-Score: 0.75\nAccuracy: 0.82\nVersion: v9", stderr=""
        )

        result = await retraining_job.execute_retraining()

        assert result["success"] is True
        # Versão extraída do parse ou fallback
        assert result["job_id"] is not None

    @patch("neural_hive_ml.retraining_job.subprocess.run")
    async def test_execute_retraining_failure(self, mock_run, retraining_job):
        """Testa execução de retreino com falha."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Training failed")

        result = await retraining_job.execute_retraining()

        assert result["success"] is False
        assert "error" in result


class TestValidateModel:
    """Testes de validate_model."""

    async def test_validate_model_improves(self, retraining_job, mock_model_repo):
        """Testa que modelo melhora o suficiente."""
        mock_model_repo.get_active_model = AsyncMock(
            return_value={"version": "v8", "f1_score": 0.73}
        )

        new_metrics = {"f1_score": 0.79, "accuracy": 0.84}

        result = await retraining_job.validate_model(new_metrics)

        assert result["should_deploy"] is True
        assert abs(result["f1_improvement"] - 0.06) < 0.001

    async def test_validate_model_no_improvement(self, retraining_job, mock_model_repo):
        """Testa que modelo não melhora o suficiente."""
        mock_model_repo.get_active_model = AsyncMock(
            return_value={"version": "v8", "f1_score": 0.73}
        )

        new_metrics = {"f1_score": 0.74, "accuracy": 0.81}

        result = await retraining_job.validate_model(new_metrics)

        assert result["should_deploy"] is False

    async def test_validate_model_no_baseline(self, retraining_job, mock_model_repo):
        """Testa quando não há baseline (primeiro modelo)."""
        mock_model_repo.get_active_model = AsyncMock(return_value=None)

        new_metrics = {"f1_score": 0.70, "accuracy": 0.80}

        result = await retraining_job.validate_model(new_metrics)

        assert result["should_deploy"] is True


class TestRegisterToMLflow:
    """Testes de register_to_mlflow."""

    async def test_register_to_mlflow_success(self, retraining_job, mock_mlflow_client):
        """Testa registro no MLflow."""
        mock_model = MagicMock()

        result = await retraining_job.register_to_mlflow(
            model=mock_model, version="v9", metrics={"f1_score": 0.75}, params={"n_estimators": 100}
        )

        mock_mlflow_client.log_model.assert_called_once()
        assert result["version"] == "v9"


class TestPublishKafkaEvent:
    """Testes de publish_kafka_event."""

    async def test_publish_trained_event(self, retraining_job, mock_kafka_producer):
        """Testa publicação de evento modelo treinado."""
        result = await retraining_job.publish_kafka_event(
            event_type="model_trained", version="v9", f1_score=0.75
        )

        mock_kafka_producer.produce_and_wait.assert_called_once()
        assert result is True


class TestRunRetraining:
    """Testes de run_retraining (end-to-end)."""

    @patch("neural_hive_ml.retraining_job.subprocess.run")
    async def test_run_retraining_success(
        self, mock_run, retraining_job, mock_model_repo, mock_mlflow_client
    ):
        """Testa fluxo completo de retreino com sucesso."""
        # Setup mocks
        mock_model_repo.db.specialist_feedback.count_documents = AsyncMock(return_value=150)
        mock_model_repo.get_active_model = AsyncMock(
            return_value={"version": "v8", "f1_score": 0.70}
        )
        mock_run.return_value = MagicMock(returncode=0, stdout="F1-Score: 0.78\nAccuracy: 0.85")
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
            "completed_at": datetime.now(),
        }

        result = await retraining_job.get_job_status("retrain-123")

        assert result["status"] == "completed"

    async def test_get_job_status_not_found(self, retraining_job):
        """Testa status de job não encontrado."""
        result = await retraining_job.get_job_status("nonexistent")

        assert result is None


# =============================================================================
# Novos Testes para Cobertura Adicional (+10 testes)
# =============================================================================


class TestCountPendingSamples:
    """Testes de _count_pending_samples."""

    async def test_count_pending_samples_with_db_access(self, retraining_job, mock_model_repo):
        """Testa contagem de samples com acesso ao MongoDB."""
        # Mock que retorna db attribute
        mock_db = AsyncMock()
        mock_db.specialist_feedback.count_documents = AsyncMock(return_value=125)

        mock_model_repo.db = mock_db

        result = await retraining_job._count_pending_samples()

        assert result == 125

    async def test_count_pending_samples_no_db_access(self, retraining_job, mock_model_repo):
        """Testa contagem quando não há acesso ao db."""
        # Remover db attribute
        mock_model_repo.db = None

        result = await retraining_job._count_pending_samples()

        assert result == 0

    async def test_count_pending_samples_with_error(self, retraining_job, mock_model_repo):
        """Testa contagem quando ocorre erro."""
        mock_db = AsyncMock()
        mock_db.specialist_feedback.count_documents = AsyncMock(side_effect=Exception("DB error"))
        mock_model_repo.db = mock_db

        result = await retraining_job._count_pending_samples()

        assert result == 0


class TestParseTrainingOutput:
    """Testes de _parse_training_output."""

    def test_parse_f1_score(self, retraining_job):
        """Testa extração de F1 score do output."""
        output = "Training complete\nF1-Score: 0.75\nAccuracy: 0.82"

        result = retraining_job._parse_training_output(output)

        assert result["f1_score"] == 0.75

    def test_parse_accuracy(self, retraining_job):
        """Testa extração de accuracy do output."""
        output = "Metrics:\naccuracy: 0.85\nf1_score: 0.78"

        result = retraining_job._parse_training_output(output)

        assert result["accuracy"] == 0.85

    def test_parse_multiple_metrics(self, retraining_job):
        """Testa extração de múltiplas métricas."""
        output = "F1-Score: 0.75\nAccuracy: 0.82\nPrecision: 0.80"

        result = retraining_job._parse_training_output(output)

        assert "f1_score" in result
        assert "accuracy" in result
        assert result["f1_score"] == 0.75
        assert result["accuracy"] == 0.82

    def test_parse_empty_output(self, retraining_job):
        """Testa parse de output vazio."""
        result = retraining_job._parse_training_output("")

        assert result == {}


class TestRunRetrainingEdgeCases:
    """Testes de edge cases para run_retraining."""

    @patch("neural_hive_ml.retraining_job.subprocess.run")
    async def test_run_retraining_insufficient_samples(
        self, mock_run, retraining_job, mock_model_repo
    ):
        """Testa retreino quando não há samples suficientes."""
        mock_model_repo.count_pending_samples = AsyncMock(return_value=50)

        result = await retraining_job.run_retraining()

        assert result["success"] is False
        assert "Insufficient samples" in result.get("reason", "")

    @patch("neural_hive_ml.retraining_job.subprocess.run")
    async def test_run_retraining_force_mode(
        self, mock_run, retraining_job, mock_model_repo, mock_mlflow_client
    ):
        """Testa retreino forçado (ignora threshold)."""
        # Setup mocks
        mock_model_repo.get_active_model = AsyncMock(
            return_value={"version": "v8", "f1_score": 0.70}
        )
        mock_run.return_value = MagicMock(returncode=0, stdout="F1-Score: 0.75\nAccuracy: 0.82")
        mock_model = MagicMock()

        # force=True deve ignorar verificação de threshold
        result = await retraining_job.run_retraining(model=mock_model, force=True)

        assert result["success"] is True


class TestRegisterToMLflowWithFeatureImportance:
    """Testes de register_to_mlflow com feature importance."""

    async def test_register_with_feature_importance(self, retraining_job, mock_mlflow_client):
        """Testa registro com feature importance."""
        mock_model = MagicMock()
        feature_importance = {
            "confidence": 0.6147,
            "rf_ml_risk": 0.2221,
            "rf_ml_confidence": 0.1632,
        }

        result = await retraining_job.register_to_mlflow(
            model=mock_model,
            version="v10",
            metrics={"f1_score": 0.75},
            params={},
            feature_importance=feature_importance,
            n_samples=500,
        )

        assert result["success"] is True
        mock_mlflow_client.log_model.assert_called_once()


class TestPublishKafkaEventErrorHandling:
    """Testes de tratamento de erro em publish_kafka_event."""

    async def test_publish_event_without_producer(self, retraining_job):
        """Testa publicação quando não há producer."""
        retraining_job.kafka_producer = None

        result = await retraining_job.publish_kafka_event(event_type="model_trained", version="v9")

        # Deve retornar False mas não lançar erro
        assert result is False

    async def test_publish_event_with_producer_error(self, retraining_job, mock_kafka_producer):
        """Testa publicação quando producer falha."""
        mock_kafka_producer.produce_and_wait = AsyncMock(
            side_effect=Exception("Kafka connection error")
        )

        result = await retraining_job.publish_kafka_event(event_type="model_trained", version="v9")

        # Deve retornar False em caso de erro
        assert result is False
