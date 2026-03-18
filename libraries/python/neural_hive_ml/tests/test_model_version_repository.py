"""Testes para ModelVersionRepository - Model Versions History."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from motor.motor_asyncio import AsyncIOMotorClientSession
from neural_hive_ml.model_version_repository import ModelVersionRepository

pytest_plugins = ('pytest_asyncio',)


@pytest.fixture
def mock_db():
    """Mock MongoDB database."""
    db = Mock()
    collection = Mock()
    db.model_versions = collection
    return db


@pytest.fixture
def repository(mock_db):
    """Fixture para ModelVersionRepository."""
    return ModelVersionRepository(mock_db)


@pytest.fixture
def sample_model_version():
    """Model version de exemplo."""
    return {
        "_id": "507f1f77bcf86cd799439011",
        "version": "v9",
        "mlflow_run_id": "run-123",
        "stage": "staging",
        "is_active": False,
        "f1_score": 0.75,
        "accuracy": 0.82,
        "precision": 0.78,
        "recall": 0.73,
        "n_samples": 500,
        "feature_importance": {
            "confidence": 0.6147,
            "rf_ml_risk": 0.2221,
            "rf_ml_confidence": 0.1632
        },
        "created_at": datetime.now(),
        "promoted_at": None,
        "promoted_by": None
    }


class TestModelVersionRepositoryInit:
    """Testes de inicialização."""

    def test_init_with_db(self, mock_db):
        """Testa inicialização com database."""
        repo = ModelVersionRepository(mock_db)
        assert repo.db == mock_db
        assert repo.collection == mock_db.model_versions


class TestCreate:
    """Testes de create."""

    @pytest.mark.asyncio
    async def test_create_success(self, repository, mock_db, sample_model_version):
        """Testa criação com sucesso."""
        mock_db.model_versions.insert_one = AsyncMock(return_value=Mock(inserted_id="new-id"))

        result = await repository.create(
            version="v9",
            mlflow_run_id="run-123",
            stage="staging",
            f1_score=0.75,
            accuracy=0.82,
            precision=0.78,
            recall=0.73,
            n_samples=500,
            feature_importance={"confidence": 0.6147}
        )

        mock_db.model_versions.insert_one.assert_called_once()
        assert result["version"] == "v9"
        assert result["mlflow_run_id"] == "run-123"

    async def test_create_with_drift_metrics(self, repository, mock_db):
        """Testa criação com drift metrics."""
        mock_db.model_versions.insert_one = AsyncMock(return_value=Mock(inserted_id="new-id"))

        drift_metrics = {
            "last_check": datetime.now(),
            "confidence_drop": 0.02,
            "approve_rate_change": 0.05
        }

        result = await repository.create(
            version="v9",
            mlflow_run_id="run-123",
            stage="production",
            f1_score=0.75,
            accuracy=0.82,
            precision=0.78,
            recall=0.73,
            n_samples=500,
            drift_metrics=drift_metrics
        )

        assert result["drift_metrics"] == drift_metrics


class TestGetById:
    """Testes de get_by_id."""

    async def test_get_by_id_success(self, repository, mock_db, sample_model_version):
        """Testa busca por ID com sucesso."""
        mock_db.model_versions.find_one = AsyncMock(return_value=sample_model_version)

        result = await repository.get_by_id("507f1f77bcf86cd799439011")

        mock_db.model_versions.find_one.assert_called_once_with({"_id": "507f1f77bcf86cd799439011"})
        assert result["version"] == "v9"

    async def test_get_by_id_not_found(self, repository, mock_db):
        """Testa busca por ID não encontrado."""
        mock_db.model_versions.find_one = AsyncMock(return_value=None)

        result = await repository.get_by_id("nonexistent-id")
        assert result is None


class TestGetByVersion:
    """Testes de get_by_version."""

    async def test_get_by_version_success(self, repository, mock_db, sample_model_version):
        """Testa busca por versão com sucesso."""
        mock_db.model_versions.find_one = AsyncMock(return_value=sample_model_version)

        result = await repository.get_by_version("v9")

        mock_db.model_versions.find_one.assert_called_once_with({"version": "v9"})
        assert result["version"] == "v9"

    async def test_get_by_version_not_found(self, repository, mock_db):
        """Testa busca por versão não encontrado."""
        mock_db.model_versions.find_one = AsyncMock(return_value=None)

        result = await repository.get_by_version("v99")
        assert result is None


class TestGetActiveModel:
    """Testes de get_active_model."""

    async def test_get_active_model_success(self, repository, mock_db):
        """Testa busca de modelo ativo."""
        mock_db.model_versions.find_one = AsyncMock(return_value={
            "_id": "id-123",
            "version": "v8",
            "stage": "production",
            "is_active": True,
            "f1_score": 0.73
        })

        result = await repository.get_active_model()

        mock_db.model_versions.find_one.assert_called_once_with(
            {"stage": "production", "is_active": True},
            sort=[("created_at", -1)]
        )
        assert result["version"] == "v8"
        assert result["is_active"] is True

    async def test_get_active_model_none(self, repository, mock_db):
        """Testa busca quando não há modelo ativo."""
        mock_db.model_versions.find_one = AsyncMock(return_value=None)

        result = await repository.get_active_model()
        assert result is None


class TestListModels:
    """Testes de list_models."""

    async def test_list_models_all(self, repository, mock_db):
        """Testa listagem de todos os modelos."""
        cursor_mock = AsyncMock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"version": "v8", "stage": "production", "is_active": True},
            {"version": "v9", "stage": "staging", "is_active": False}
        ])
        cursor_mock.limit = Mock(return_value=cursor_mock)
        cursor_mock.skip = Mock(return_value=cursor_mock)
        mock_db.model_versions.find.return_value = cursor_mock

        result = await repository.list_models()

        assert len(result) == 2
        assert result[0]["version"] == "v8"
        assert result[1]["version"] == "v9"

    async def test_list_models_with_stage_filter(self, repository, mock_db):
        """Testa listagem com filtro de stage."""
        cursor_mock = AsyncMock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"version": "v9", "stage": "staging", "is_active": False}
        ])
        cursor_mock.limit = Mock(return_value=cursor_mock)
        cursor_mock.skip = Mock(return_value=cursor_mock)
        mock_db.model_versions.find.return_value = cursor_mock

        result = await repository.list_models(stage="staging")

        mock_db.model_versions.find.assert_called_once_with({"stage": "staging"})
        assert len(result) == 1

    async def test_list_models_with_is_active_filter(self, repository, mock_db):
        """Testa listagem com filtro is_active."""
        cursor_mock = AsyncMock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"version": "v8", "stage": "production", "is_active": True}
        ])
        cursor_mock.limit = Mock(return_value=cursor_mock)
        cursor_mock.skip = Mock(return_value=cursor_mock)
        mock_db.model_versions.find.return_value = cursor_mock

        result = await repository.list_models(is_active=True)

        mock_db.model_versions.find.assert_called_once_with({"is_active": True})
        assert len(result) == 1

    async def test_list_models_with_limit_offset(self, repository, mock_db):
        """Testa listagem com paginação."""
        cursor_mock = AsyncMock()
        cursor_mock.to_list = AsyncMock(return_value=[])
        cursor_mock.skip = Mock(return_value=cursor_mock)
        cursor_mock.limit = Mock(return_value=cursor_mock)
        mock_db.model_versions.find = Mock(return_value=cursor_mock)

        await repository.list_models(limit=10, offset=20)

        cursor_mock.skip.assert_called_once_with(20)
        cursor_mock.limit.assert_called_once_with(10)


class TestUpdate:
    """Testes de update."""

    async def test_update_success(self, repository, mock_db):
        """Testa atualização com sucesso."""
        mock_db.model_versions.update_one = AsyncMock(return_value=Mock(modified_count=1))

        result = await repository.update(
            version="v9",
            stage="production",
            is_active=True,
            promoted_at=datetime.now()
        )

        mock_db.model_versions.update_one.assert_called_once()
        assert result is True

    async def test_update_not_found(self, repository, mock_db):
        """Testa atualização de versão não encontrada."""
        mock_db.model_versions.update_one = AsyncMock(return_value=Mock(modified_count=0))

        result = await repository.update(
            version="v99",
            stage="production"
        )

        assert result is False


class TestUpdateDriftMetrics:
    """Testes de update_drift_metrics."""

    async def test_update_drift_metrics_success(self, repository, mock_db):
        """Testa atualização de drift metrics."""
        mock_db.model_versions.update_one = AsyncMock(return_value=Mock(modified_count=1))

        drift_metrics = {
            "last_check": datetime.now(),
            "confidence_drop": 0.05,
            "approve_rate_change": 0.08
        }

        result = await repository.update_drift_metrics("v9", drift_metrics)

        mock_db.model_versions.update_one.assert_called_once_with(
            {"version": "v9"},
            {"$set": {"drift_metrics": drift_metrics}}
        )
        assert result is True

    async def test_update_drift_metrics_not_found(self, repository, mock_db):
        """Testa atualização de drift metrics em versão não encontrada."""
        mock_db.model_versions.update_one = AsyncMock(return_value=Mock(modified_count=0))

        result = await repository.update_drift_metrics("v99", {})

        assert result is False


class TestPromoteModel:
    """Testes de promote_model."""

    async def test_promote_to_production(self, repository, mock_db):
        """Testa promoção para production."""
        mock_db.model_versions.update_one = AsyncMock(return_value=Mock(modified_count=1))
        mock_db.model_versions.find_one = AsyncMock(return_value=None)  # Sem modelo ativo anterior
        promoted_at = datetime.now()

        result = await repository.promote_model(
            version="v9",
            stage="production",
            promoted_at=promoted_at,
            promoted_by="canary"
        )

        mock_db.model_versions.update_one.assert_called_once()
        assert result is True

    async def test_promote_archives_current(self, repository, mock_db):
        """Testa que promoção arquiva modelo atual."""
        # Mock para find_one (modelo atual)
        mock_db.model_versions.find_one = AsyncMock(return_value={
            "version": "v8",
            "stage": "production",
            "is_active": True
        })
        # Mock para update_one (arquivar e promover)
        mock_db.model_versions.update_one = AsyncMock(return_value=Mock(modified_count=1))

        result = await repository.promote_model(
            version="v9",
            stage="production",
            archive_current=True
        )

        # Verifica que chamou update_one duas vezes (arquivar + promover)
        assert mock_db.model_versions.update_one.call_count == 2
        assert result is True


class TestDeactivateModel:
    """Testes de deactivate_model."""

    async def test_deactivate_success(self, repository, mock_db):
        """Testa desativação de modelo."""
        mock_db.model_versions.update_one = AsyncMock(return_value=Mock(modified_count=1))

        result = await repository.deactivate_model("v8")

        mock_db.model_versions.update_one.assert_called_once_with(
            {"version": "v8"},
            {"$set": {"is_active": False}}
        )
        assert result is True


class TestDelete:
    """Testes de delete."""

    async def test_delete_success(self, repository, mock_db):
        """Testa deleção com sucesso."""
        mock_db.model_versions.delete_one = AsyncMock(return_value=Mock(deleted_count=1))

        result = await repository.delete("v9")

        mock_db.model_versions.delete_one.assert_called_once_with({"version": "v9"})
        assert result is True

    async def test_delete_not_found(self, repository, mock_db):
        """Testa deleção de versão não encontrada."""
        mock_db.model_versions.delete_one = AsyncMock(return_value=Mock(deleted_count=0))

        result = await repository.delete("v99")
        assert result is False


class TestGetModelHistory:
    """Testes de get_model_history."""

    async def test_get_model_history(self, repository, mock_db):
        """Testa busca de histórico de versões."""
        cursor_mock = AsyncMock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"version": "v7", "stage": "archived", "created_at": datetime.now() - timedelta(days=2)},
            {"version": "v8", "stage": "production", "created_at": datetime.now() - timedelta(days=1)},
            {"version": "v9", "stage": "staging", "created_at": datetime.now()}
        ])
        cursor_mock.skip = Mock(return_value=cursor_mock)
        cursor_mock.limit = Mock(return_value=cursor_mock)
        mock_db.model_versions.find.return_value.sort.return_value = cursor_mock

        result = await repository.get_model_history(limit=10)

        assert len(result) == 3
        assert result[0]["version"] == "v7"
        assert result[2]["version"] == "v9"
