"""Testes para MLflowClient - Approval Models."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from neural_hive_ml.mlflow_client import MLflowClient


@pytest.fixture
def mock_mlflow():
    """Mock MLflow."""
    with patch('neural_hive_ml.mlflow_client.mlflow') as mock:
        mock.get_experiment_by_name.return_value = None
        mock.create_experiment.return_value = "exp-123"
        mock_run_info = MagicMock()
        mock_run_info.run_id = "run-123"
        mock.start_run.return_value = MagicMock(
            __enter__=MagicMock(return_value=MagicMock(info=mock_run_info)),
            __exit__=MagicMock(return_value=False)
        )
        mock.sklearn.log_model.return_value = MagicMock(registered_model_version="v9")
        yield mock


@pytest.fixture
def mock_mlflow_client():
    """Mock MLflow Client."""
    with patch('neural_hive_ml.mlflow_client.MlflowClient') as mock:
        client_instance = MagicMock()
        client_instance.get_latest_versions.return_value = [
            MagicMock(
                version="9",
                current_stage="Staging",
                run_id="run-123",
                creation_timestamp=1234567890000
            )
        ]
        client_instance.get_run.return_value = MagicMock(
            data=MagicMock(
                metrics={"f1_score": 0.75, "accuracy": 0.82},
                params={"n_estimators": 100},
                tags={"training_date": "2026-03-18"}
            )
        )
        mock.return_value = client_instance
        yield mock


@pytest.fixture
def mlflow_client(mock_mlflow, mock_mlflow_client):
    """Fixture para MLflowClient."""
    return MLflowClient(tracking_uri="http://localhost:5000")


class TestMLflowClientInit:
    """Testes de inicialização."""

    def test_init_with_tracking_uri(self, mock_mlflow):
        """Testa inicialização com tracking URI."""
        client = MLflowClient(tracking_uri="http://mlflow:5000")
        mock_mlflow.set_tracking_uri.assert_called_once_with("http://mlflow:5000")
        assert client.experiment_prefix == "approval-models"

    def test_init_default(self):
        """Testa inicialização com valores padrão."""
        with patch('neural_hive_ml.mlflow_client.mlflow'):
            with patch('neural_hive_ml.mlflow_client.MlflowClient'):
                client = MLflowClient()
                assert client.experiment_prefix == "approval-models"


class TestLogModel:
    """Testes de log_model."""

    def test_log_model_success(self, mlflow_client, mock_mlflow):
        """Testa logging de modelo com sucesso."""
        mock_model = MagicMock()

        result = mlflow_client.log_model(
            model=mock_model,
            version="v9",
            metrics={
                "f1_score": 0.75,
                "accuracy": 0.82,
                "precision": 0.78,
                "recall": 0.73
            },
            params={"n_estimators": 100, "max_depth": 5},
            feature_importance={
                "confidence": 0.6147,
                "rf_ml_risk": 0.2221,
                "rf_ml_confidence": 0.1632
            },
            n_samples=500
        )

        assert result == "v9"
        mock_mlflow.log_metric.assert_any_call("f1_score", 0.75)
        mock_mlflow.log_metric.assert_any_call("accuracy", 0.82)
        mock_mlflow.set_tag.assert_any_call("feature_importance_confidence", 0.6147)

    def test_log_model_with_run_id(self, mlflow_client, mock_mlflow):
        """Testa logging com run_id específico."""
        mock_model = MagicMock()
        mock_mlflow.start_run.return_value = MagicMock(
            __enter__=MagicMock(return_value=MagicMock()),
            __exit__=MagicMock(return_value=False)
        )

        mlflow_client.log_model(
            model=mock_model,
            version="v9",
            metrics={"f1_score": 0.75},
            params={},
            run_id="existing-run-123",
            n_samples=100
        )

        # Verifica que usou o run_id existente
        mock_mlflow.start_run.assert_called_once_with(run_id="existing-run-123")

    def test_log_model_error(self, mlflow_client, mock_mlflow):
        """Testa tratamento de erro no logging."""
        mock_mlflow.start_run.side_effect = Exception("MLflow error")

        with pytest.raises(Exception) as exc_info:
            mlflow_client.log_model(
                model=MagicMock(),
                version="v9",
                metrics={},
                params={}
            )
        assert "MLflow error" in str(exc_info.value)


class TestRegisterModel:
    """Testes de register_model."""

    def test_register_model_new(self, mlflow_client, mock_mlflow):
        """Testa registro de novo modelo."""
        mock_mlflow.register_model.return_value = MagicMock(version="9")

        mlflow_client.register_model(
            model_name="approval-model-v9",
            run_id="run-123"
        )

        # Verifica que register_model foi chamado
        mock_mlflow.register_model.assert_called_once_with(
            artifact_uri="runs:/run-123/model",
            name="approval-model-v9"
        )

    def test_register_model_existing(self, mlflow_client, mock_mlflow):
        """Testa registro em experimento existente."""
        mock_exp = MagicMock(experiment_id="exp-789")
        mock_mlflow.get_experiment_by_name.return_value = mock_exp

        mlflow_client.register_model(
            model_name="approval-model-v9",
            run_id="run-123"
        )

        # Não deve criar novo experimento
        mock_mlflow.create_experiment.assert_not_called()


class TestGetModelVersion:
    """Testes de get_model_version."""

    def test_get_model_version_success(self, mlflow_client):
        """Testa busca de versão de modelo com sucesso."""
        result = mlflow_client.get_model_version("approval-model-v9")

        assert result["version"] == "9"
        assert result["stage"] == "Staging"
        assert result["f1_score"] == 0.75
        assert result["accuracy"] == 0.82
        assert result["params"]["n_estimators"] == 100

    def test_get_model_version_not_found(self, mlflow_client):
        """Testa busca de versão inexistente."""
        from mlflow.exceptions import MlflowException
        mlflow_client.client.get_latest_versions.side_effect = MlflowException("Not found")

        result = mlflow_client.get_model_version("nonexistent-model")
        assert result is None

    def test_get_model_version_with_metrics_extraction(self, mlflow_client):
        """Testa extração correta de métricas."""
        result = mlflow_client.get_model_version("approval-model-v9")

        assert "metrics" in result
        assert result["metrics"]["f1_score"] == 0.75
        assert result["metrics"]["accuracy"] == 0.82


class TestPromoteModel:
    """Testes de promote_model."""

    def test_promote_to_staging(self, mlflow_client):
        """Testa promoção para staging."""
        mlflow_client.promote_model(
            model_name="approval-model-v9",
            version="9",
            stage="Staging"
        )

        mlflow_client.client.transition_model_version_stage.assert_called_once_with(
            name="approval-model-v9",
            version="9",
            stage="Staging"
        )

    def test_promote_to_production_archives_old(self, mlflow_client):
        """Testa que promoção para production arquiva versão anterior."""
        old_version = MagicMock(version="8", current_stage="Production")
        mlflow_client.client.get_latest_versions.return_value = [old_version]

        mlflow_client.promote_model(
            model_name="approval-model-v9",
            version="9",
            stage="Production"
        )

        # Verifica que versão antiga foi arquivada
        assert mlflow_client.client.transition_model_version_stage.call_count == 2

    def test_promote_model_error(self, mlflow_client):
        """Testa tratamento de erro na promoção."""
        from mlflow.exceptions import MlflowException
        mlflow_client.client.transition_model_version_stage.side_effect = MlflowException("Error")

        with pytest.raises(MlflowException):
            mlflow_client.promote_model(
                model_name="approval-model-v9",
                version="9",
                stage="Production"
            )


class TestListModels:
    """Testes de list_models."""

    def test_list_models_all(self, mlflow_client):
        """Testa listagem de todos os modelos."""
        model1 = MagicMock()
        model1.name = "approval-model-v8"
        model1.creation_timestamp = 123000
        model1.last_updated_timestamp = 456000
        model1.description = None
        model1.latest_versions = []

        model2 = MagicMock()
        model2.name = "approval-model-v9"
        model2.creation_timestamp = 124000
        model2.last_updated_timestamp = 457000
        model2.description = None
        model2.latest_versions = []

        mlflow_client.client.search_registered_models.return_value = [model1, model2]

        result = mlflow_client.list_models()

        assert len(result) == 2
        assert result[0]["name"] == "approval-model-v8"
        assert result[1]["name"] == "approval-model-v9"

    def test_list_models_with_filter(self, mlflow_client):
        """Testa listagem com filtro."""
        mlflow_client.client.search_registered_models.return_value = []

        mlflow_client.list_models(filter_string="name like 'approval-model%'")

        mlflow_client.client.search_registered_models.assert_called_once_with(
            filter_string="name like 'approval-model%'"
        )


class TestGetLatestRunId:
    """Testes de get_latest_run_id."""

    def test_get_latest_run_id_success(self, mlflow_client):
        """Testa busca do run_id mais recente."""
        result = mlflow_client.get_latest_run_id("approval-model-v9")

        assert result == "run-123"

    def test_get_latest_run_id_not_found(self, mlflow_client):
        """Testa busca quando não há versões."""
        mlflow_client.client.get_latest_versions.return_value = []

        result = mlflow_client.get_latest_run_id("approval-model-v9")
        assert result is None


class TestDeleteModel:
    """Testes de delete_model."""

    def test_delete_model_success(self, mlflow_client):
        """Testa deleção de modelo."""
        mlflow_client.delete_model(
            model_name="approval-model-v9",
            version="9"
        )

        mlflow_client.client.delete_model_version.assert_called_once_with(
            name="approval-model-v9",
            version="9"
        )


# =============================================================================
# Novos Testes para Cobertura Adicional (+10 testes)
# =============================================================================

class TestGetRunHistory:
    """Testes de get_run_history."""

    def test_get_run_history_success(self, mlflow_client, mock_mlflow):
        """Testa busca de histórico de runs."""
        # Mock experiment
        mock_exp = MagicMock()
        mock_exp.experiment_id = "exp-123"
        mock_mlflow.get_experiment_by_name.return_value = mock_exp

        # Mock runs
        mock_run = MagicMock()
        mock_run.info.run_id = "run-123"
        mock_run.info.start_time = 1234567890000
        mock_run.info.status = "COMPLETED"
        mock_run.data.metrics = {"f1_score": 0.75}
        mock_run.data.params = {"n_estimators": 100}

        mlflow_client.client.search_runs.return_value = [mock_run]

        result = mlflow_client.get_run_history("v9", limit=10)

        assert len(result) == 1
        assert result[0]["run_id"] == "run-123"

    def test_get_run_history_no_experiment(self, mlflow_client, mock_mlflow):
        """Testa histórico quando experimento não existe."""
        mock_mlflow.get_experiment_by_name.return_value = None

        result = mlflow_client.get_run_history("nonexistent")

        assert result == []

    def test_get_run_history_with_limit(self, mlflow_client, mock_mlflow):
        """Testa histórico com limite de resultados."""
        mock_exp = MagicMock()
        mock_exp.experiment_id = "exp-123"
        mock_mlflow.get_experiment_by_name.return_value = mock_exp
        mlflow_client.client.search_runs.return_value = []

        mlflow_client.get_run_history("v9", limit=5)

        # Verifica que search_runs foi chamado com max_results=5
        mlflow_client.client.search_runs.assert_called_once()
        call_kwargs = mlflow_client.client.search_runs.call_args[1]
        assert call_kwargs["max_results"] == 5


class TestPromoteModelVariations:
    """Testes de variações de promote_model."""

    def test_promote_without_archiving_current(self, mlflow_client):
        """Testa promoção sem arquivar versão atual."""
        mlflow_client.client.get_latest_versions.return_value = []

        mlflow_client.promote_model(
            model_name="approval-model-v9",
            version="9",
            stage="Production",
            archive_current=False
        )

        # Deve chamar transition apenas uma vez
        assert mlflow_client.client.transition_model_version_stage.call_count == 1

    def test_promote_to_archived_stage(self, mlflow_client):
        """Testa promoção para Archived."""
        mlflow_client.promote_model(
            model_name="approval-model-v9",
            version="8",
            stage="Archived",
            archive_current=False
        )

        mlflow_client.client.transition_model_version_stage.assert_called_once_with(
            name="approval-model-v9",
            version="8",
            stage="Archived"
        )


class TestLogModelWithTags:
    """Testes de log_model com tags."""

    def test_log_model_with_custom_tags(self, mlflow_client, mock_mlflow):
        """Testa logging com tags customizadas."""
        mock_model = MagicMock()

        custom_tags = {
            "training_date": "2026-03-30",
            "dataset_version": "v2.0"
        }

        mlflow_client.log_model(
            model=mock_model,
            version="v10",
            metrics={"f1_score": 0.75},
            params={},
            tags=custom_tags,
            n_samples=500
        )

        # Verifica que tags foram setadas
        assert mock_mlflow.set_tag.called


class TestGetModelVersionWithFeatureImportance:
    """Testes de get_model_version com feature importance."""

    def test_get_model_version_extracts_feature_importance(self, mlflow_client):
        """Testa extração de feature importance das tags."""
        # Mock run com feature importance nas tags
        mlflow_client.client.get_run.return_value = MagicMock(
            data=MagicMock(
                metrics={"f1_score": 0.75},
                params={},
                tags={
                    "feature_importance_confidence": "0.6147",
                    "feature_importance_rf_ml_risk": "0.2221",
                    "model_type": "approval"
                }
            )
        )

        result = mlflow_client.get_model_version("approval-model-v9")

        assert "feature_importance" in result
        assert result["feature_importance"]["confidence"] == 0.6147
        assert result["feature_importance"]["rf_ml_risk"] == 0.2221


class TestListModelsVariations:
    """Testes de variações de list_models."""

    def test_list_models_empty(self, mlflow_client):
        """Testa listagem quando não há modelos."""
        mlflow_client.client.search_registered_models.return_value = []

        result = mlflow_client.list_models()

        assert result == []

    def test_list_models_with_description(self, mlflow_client):
        """Testa listagem com descrição."""
        model = MagicMock()
        model.name = "approval-model-v9"
        model.creation_timestamp = 123000
        model.last_updated_timestamp = 456000
        model.description = "Latest approval model"
        model.latest_versions = []

        mlflow_client.client.search_registered_models.return_value = [model]

        result = mlflow_client.list_models()

        assert result[0]["description"] == "Latest approval model"


class TestDeleteModelErrorHandling:
    """Testes de tratamento de erro em delete_model."""

    def test_delete_model_with_mlflow_exception(self, mlflow_client):
        """Testa deleção quando MLflow lança exceção."""
        from mlflow.exceptions import MlflowException
        mlflow_client.client.delete_model_version.side_effect = MlflowException("Not found")

        with pytest.raises(MlflowException):
            mlflow_client.delete_model(
                model_name="approval-model-v9",
                version="9"
            )
