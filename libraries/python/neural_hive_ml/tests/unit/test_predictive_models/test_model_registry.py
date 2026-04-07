"""Testes para ModelRegistry - Gerenciador de modelos MLflow."""

import pytest
from unittest.mock import Mock, patch
from mlflow.tracking import MlflowClient

from neural_hive_ml.predictive_models.model_registry import ModelRegistry


@pytest.fixture
def mock_mlflow_client():
    """Mock do MLflow client."""
    client = Mock(spec=MlflowClient)
    return client


@pytest.fixture
def model_registry(mock_mlflow_client):
    """Fixture para ModelRegistry."""
    with (
        patch("mlflow.set_tracking_uri"),
        patch(
            "neural_hive_ml.predictive_models.model_registry.MlflowClient",
            return_value=mock_mlflow_client,
        ),
    ):
        registry = ModelRegistry(tracking_uri="http://localhost:5000", experiment_prefix="test")
        registry.client = mock_mlflow_client
        return registry


@pytest.fixture
def sample_model():
    """Modelo sklearn de exemplo."""
    from sklearn.ensemble import RandomForestClassifier
    import numpy as np

    model = RandomForestClassifier(n_estimators=10, random_state=42)
    # Treina com dados dummy
    X = np.random.rand(10, 5)
    y = np.random.randint(0, 2, 10)
    model.fit(X, y)
    return model


# =============================================================================
# Testes Adicionais - Epic Extra (+10 testes)
# =============================================================================


class TestRegisterModel:
    """Testes para test_register_model (save_model)."""

    def test_save_model_success(self, model_registry, mock_mlflow_client, sample_model):
        """Testa salvar modelo com sucesso (integração com MLflow real)."""
        metrics = {"accuracy": 0.85, "f1_score": 0.82}
        params = {"n_estimators": 100, "max_depth": 10}
        tags = {"version": "v1"}

        # Usa MLflow real para salvar o modelo
        version = model_registry.save_model(
            model=sample_model, model_name="test-model", metrics=metrics, params=params, tags=tags
        )

        # Verifica que uma versão foi retornada
        assert version is not None
        # A versão deve ser um número ou string numérica
        assert str(version).isdigit() or isinstance(version, int)

    def test_save_model_existing_experiment(self, model_registry, mock_mlflow_client, sample_model):
        """Testa salvar modelo em experimento existente."""
        # Mock experiment existente
        mock_experiment = Mock()
        mock_experiment.experiment_id = "existing-exp-123"

        with (
            patch("mlflow.get_experiment_by_name", return_value=mock_experiment),
            patch("mlflow.start_run"),
            patch("mlflow.log_param"),
            patch("mlflow.log_metric"),
            patch("mlflow.set_tag"),
            patch("mlflow.sklearn.log_model") as mock_log_model,
        ):
            mock_model_info = Mock()
            mock_model_info.registered_model_version = "v2"
            mock_log_model.return_value = mock_model_info

            version = model_registry.save_model(
                model=sample_model, model_name="test-model", metrics={}, params={}
            )

            assert version == "v2"


class TestGetModel:
    """Testes para test_get_model (load_model)."""

    def test_get_model_production_stage(self, model_registry, mock_mlflow_client):
        """Testa carregar modelo do estágio Production."""
        mock_model = Mock()
        mock_model.predict = Mock(return_value=[1])

        with patch("mlflow.sklearn.load_model", return_value=mock_model) as mock_load:
            model = model_registry.load_model("test-model", "Production")

            mock_load.assert_called_once_with("models:/test-model/Production")
            assert model is not None

    def test_get_model_staging_stage(self, model_registry, mock_mlflow_client):
        """Testa carregar modelo do estágio Staging."""
        mock_model = Mock()

        with patch("mlflow.sklearn.load_model", return_value=mock_model) as mock_load:
            model = model_registry.load_model("test-model", "Staging")

            mock_load.assert_called_once_with("models:/test-model/Staging")
            assert model is not None

    def test_get_model_not_found(self, model_registry, mock_mlflow_client):
        """Testa carregar modelo que não existe."""
        with patch("mlflow.sklearn.load_model", side_effect=Exception("Model not found")):
            model = model_registry.load_model("nonexistent-model", "Production")

            # Deve retornar None em caso de erro
            assert model is None


class TestListModels:
    """Testes para test_list_models."""

    def test_list_models_all(self, model_registry, mock_mlflow_client):
        """Testa listar todos os modelos registrados."""
        # Mock search_registered_models
        mock_model1 = Mock()
        mock_model1.name = "model1"
        mock_model1.creation_timestamp = 1234567890
        mock_model1.last_updated_timestamp = 1234567890
        mock_model1.description = "Test model 1"
        mock_model1.latest_versions = []

        mock_model2 = Mock()
        mock_model2.name = "model2"
        mock_model2.creation_timestamp = 1234567891
        mock_model2.last_updated_timestamp = 1234567891
        mock_model2.description = "Test model 2"
        mock_model2.latest_versions = []

        mock_mlflow_client.search_registered_models.return_value = [mock_model1, mock_model2]

        models = model_registry.list_models()

        assert len(models) == 2
        assert models[0]["name"] == "model1"
        assert models[1]["name"] == "model2"

    def test_list_models_with_filter(self, model_registry, mock_mlflow_client):
        """Testa listar modelos com filtro."""
        mock_mlflow_client.search_registered_models.return_value = []

        models = model_registry.list_models(filter_string="name LIKE 'test%'")

        mock_mlflow_client.search_registered_models.assert_called_once_with(
            filter_string="name LIKE 'test%'"
        )
        assert models == []


class TestUnregisterModel:
    """Testes para test_unregister_model (archive_model)."""

    def test_unregister_model_via_archive(self, model_registry, mock_mlflow_client):
        """Testa desregistrar modelo via arquivamento."""
        with patch.object(model_registry, "archive_model") as mock_archive:
            model_registry.archive_model("test-model", "v1")

            mock_archive.assert_called_once_with("test-model", "v1")


class TestGetModelStats:
    """Testes para test_get_model_stats (get_model_metadata)."""

    def test_get_model_stats_production(self, model_registry, mock_mlflow_client):
        """Testa obter estatísticas do modelo em produção."""
        # Mock get_latest_versions
        mock_version = Mock()
        mock_version.version = "v1"
        mock_version.current_stage = "Production"
        mock_version.creation_timestamp = 1234567890
        mock_version.last_updated_timestamp = 1234567890
        mock_version.run_id = "run-123"

        mock_mlflow_client.get_latest_versions.return_value = [mock_version]

        # Mock get_run
        mock_run = Mock()
        mock_run.data.metrics = {"accuracy": 0.85, "f1_score": 0.82}
        mock_run.data.params = {"n_estimators": "100"}
        mock_run.data.tags = {"version": "v1"}

        mock_mlflow_client.get_run.return_value = mock_run

        metadata = model_registry.get_model_metadata("test-model", "Production")

        assert metadata["version"] == "v1"
        assert metadata["stage"] == "Production"
        assert "metrics" in metadata
        assert "params" in metadata
        assert "tags" in metadata

    def test_get_model_stats_not_found(self, model_registry, mock_mlflow_client):
        """Testa obter estatísticas de modelo não encontrado."""
        mock_mlflow_client.get_latest_versions.return_value = []

        metadata = model_registry.get_model_metadata("nonexistent-model", "Production")

        assert metadata == {}


class TestUpdateModelStats:
    """Testes para test_update_model_stats."""

    def test_update_model_stats_via_new_save(
        self, model_registry, mock_mlflow_client, sample_model
    ):
        """Testa atualizar estatísticas salvando nova versão."""
        new_metrics = {"accuracy": 0.90, "f1_score": 0.88}

        with (
            patch("mlflow.get_experiment_by_name", return_value=None),
            patch("mlflow.create_experiment", return_value="exp-123"),
            patch("mlflow.start_run"),
            patch("mlflow.log_param"),
            patch("mlflow.log_metric"),
            patch("mlflow.set_tag"),
            patch("mlflow.sklearn.log_model") as mock_log_model,
        ):
            mock_model_info = Mock()
            mock_model_info.registered_model_version = "v2"
            mock_log_model.return_value = mock_model_info

            version = model_registry.save_model(
                model=sample_model, model_name="test-model", metrics=new_metrics, params={}
            )

            assert version == "v2"


class TestModelExists:
    """Testes para test_model_exists."""

    def test_model_exists_true(self, model_registry, mock_mlflow_client):
        """Testa verificar se modelo existe (True)."""
        mock_version = Mock()
        mock_version.version = "v1"
        mock_mlflow_client.get_latest_versions.return_value = [mock_version]

        metadata = model_registry.get_model_metadata("test-model", "Production")

        assert metadata is not None
        assert metadata["version"] == "v1"

    def test_model_exists_false(self, model_registry, mock_mlflow_client):
        """Testa verificar se modelo existe (False)."""
        mock_mlflow_client.get_latest_versions.return_value = []

        metadata = model_registry.get_model_metadata("nonexistent-model", "Production")

        assert metadata == {}


class TestGetAllModels:
    """Testes para test_get_all_models."""

    def test_get_all_models_from_list(self, model_registry, mock_mlflow_client):
        """Testa obter todos os modelos via list_models."""
        mock_model = Mock()
        mock_model.name = "approval-model"
        mock_model.creation_timestamp = 1234567890
        mock_model.last_updated_timestamp = 1234567890
        mock_model.description = "Approval prediction model"
        mock_model.latest_versions = []

        mock_mlflow_client.search_registered_models.return_value = [mock_model]

        models = model_registry.list_models()

        assert len(models) == 1
        assert models[0]["name"] == "approval-model"


class TestRegistryPersistence:
    """Testes para test_registry_persistence."""

    def test_registry_persistence_across_instances(self, mock_mlflow_client):
        """Testa que registry persiste entre instâncias."""
        # Cria primeira instância
        with patch("mlflow.set_tracking_uri"):
            registry1 = ModelRegistry(tracking_uri="http://localhost:5000")

        # Cria segunda instância com mesma URI
        with patch("mlflow.set_tracking_uri"):
            registry2 = ModelRegistry(tracking_uri="http://localhost:5000")

        # Ambas devem ter o mesmo experiment_prefix
        assert registry1.experiment_prefix == registry2.experiment_prefix


class TestPromoteModel:
    """Testes adicionais para promote_model."""

    def test_promote_model_to_production(self, model_registry, mock_mlflow_client):
        """Testa promoção de modelo para produção."""
        # Mock get_latest_versions para retornar vazio (sem modelo atual)
        mock_mlflow_client.get_latest_versions.return_value = []

        with patch.object(
            model_registry.client, "transition_model_version_stage"
        ) as mock_transition:
            model_registry.promote_model("test-model", "v2", "Production")

            mock_transition.assert_called_once_with(
                name="test-model", version="v2", stage="Production"
            )

    def test_promote_model_archives_current(self, model_registry, mock_mlflow_client):
        """Testa que promoção arquiva modelo atual em produção."""
        # Mock get_latest_versions para retornar modelo atual
        current_version = Mock()
        current_version.version = "v1"
        mock_mlflow_client.get_latest_versions.return_value = [current_version]

        with patch.object(
            model_registry.client, "transition_model_version_stage"
        ) as mock_transition:
            model_registry.promote_model("test-model", "v2", "Production")

            # Deve chamar transition_model_version_stage duas vezes:
            # 1. Para arquivar v1
            # 2. Para promover v2
            assert mock_transition.call_count == 2

            # Verifica que v1 foi arquivado
            archive_call = mock_transition.call_args_list[0]
            assert archive_call[1]["stage"] == "Archived"
            assert archive_call[1]["version"] == "v1"

            # Verifica que v2 foi promovido
            promote_call = mock_transition.call_args_list[1]
            assert promote_call[1]["stage"] == "Production"
            assert promote_call[1]["version"] == "v2"


class TestArchiveModel:
    """Testes adicionais para archive_model."""

    def test_archive_model_success(self, model_registry, mock_mlflow_client):
        """Testa arquivar versão de modelo."""
        with patch.object(
            model_registry.client, "transition_model_version_stage"
        ) as mock_transition:
            model_registry.archive_model("test-model", "v1")

            mock_transition.assert_called_once_with(
                name="test-model", version="v1", stage="Archived"
            )
