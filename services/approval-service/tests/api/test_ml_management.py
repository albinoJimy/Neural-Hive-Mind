"""Testes para MLManagementRouter - API de Gestão ML."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routers.ml_management import MLManagementRouter


@pytest.fixture()
def mock_mlflow_client():
    """Mock MLflowClient."""
    client = AsyncMock()
    client.log_model = AsyncMock(return_value="v9")
    client.list_models = AsyncMock(return_value=[])
    return client


@pytest.fixture()
def mock_model_repo():
    """Mock ModelVersionRepository."""
    repo = AsyncMock()
    repo.get_active_model = AsyncMock(
        return_value={"version": "v8", "f1_score": 0.73, "accuracy": 0.80}
    )
    repo.list_models = AsyncMock(return_value=[])
    repo.get_model_version = AsyncMock(return_value={"version": "v8", "stage": "production"})
    repo.promote_model = AsyncMock(return_value=True)
    repo.update_drift_metrics = AsyncMock(return_value=True)
    return repo


@pytest.fixture()
def mock_retraining_job():
    """Mock RetrainingJob."""
    job = AsyncMock()
    job.run_retraining = AsyncMock(
        return_value={"success": True, "job_id": "retrain-123", "new_version": "v9"}
    )
    job.get_job_status = AsyncMock(return_value={"job_id": "retrain-123", "status": "completed"})
    return job


@pytest.fixture()
def mock_drift_detector():
    """Mock DriftDetector."""
    detector = AsyncMock()
    detector.detect_drift = AsyncMock(
        return_value={"drift_detected": True, "confidence_drop": 0.05}
    )
    return detector


@pytest.fixture()
def app(mock_mlflow_client, mock_model_repo, mock_retraining_job, mock_drift_detector):
    """Fixture para app FastAPI com router ML."""
    app = FastAPI()
    router = MLManagementRouter(
        mlflow_client=mock_mlflow_client,
        model_repo=mock_model_repo,
        retraining_job=mock_retraining_job,
        drift_detector=mock_drift_detector,
    )
    app.include_router(router.router, prefix="/api/v1/ml")
    return app


@pytest.fixture()
def client(app):
    """Test client."""
    return TestClient(app)


class TestPostRetrain:
    """Testes POST /retrain."""

    def test_post_retrain_success(self, client, mock_retraining_job):
        """Testa POST /retrain com sucesso."""
        response = client.post("/api/v1/ml/retrain", json={"force": True})

        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "retrain-123"
        assert data["status"] == "queued"

    def test_post_retrain_with_samples(self, client, mock_retraining_job):
        """Testa POST /retrain com samples_override."""
        mock_retraining_job.run_retraining = AsyncMock(
            return_value={"success": True, "job_id": "retrain-456"}
        )

        response = client.post("/api/v1/ml/retrain", json={"force": True, "samples_override": 500})

        assert response.status_code == 202


class TestGetRetrainStatus:
    """Testes GET /retrain/{job_id}."""

    def test_get_retrain_status_completed(self, client, mock_retraining_job):
        """Testa GET /retrain/{job_id} para job completado."""
        response = client.get("/api/v1/ml/retrain/retrain-123")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "retrain-123"
        assert data["status"] == "completed"

    def test_get_retrain_status_not_found(self, client, mock_retraining_job):
        """Testa GET /retrain/{job_id} para job não encontrado."""
        mock_retraining_job.get_job_status = AsyncMock(return_value=None)

        response = client.get("/api/v1/ml/retrain/nonexistent")

        assert response.status_code == 404


class TestGetModels:
    """Testes GET /models."""

    def test_get_models_all(self, client, mock_model_repo):
        """Testa GET /models sem filtros."""
        mock_model_repo.list_models = AsyncMock(
            return_value=[
                {"version": "v8", "stage": "production", "is_active": True},
                {"version": "v9", "stage": "staging", "is_active": False},
            ]
        )

        response = client.get("/api/v1/ml/models")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["models"]) == 2

    def test_get_models_with_stage_filter(self, client, mock_model_repo):
        """Testa GET /models com filtro stage."""
        mock_model_repo.list_models = AsyncMock(
            return_value=[{"version": "v9", "stage": "staging"}]
        )

        response = client.get("/api/v1/ml/models?stage=staging")

        assert response.status_code == 200

    def test_get_models_with_limit_offset(self, client, mock_model_repo):
        """Testa GET /models com paginação."""
        response = client.get("/api/v1/ml/models?limit=10&offset=20")

        assert response.status_code == 200


class TestGetModelVersion:
    """Testes GET /models/{version}."""

    def test_get_model_version_success(self, client, mock_model_repo):
        """Testa GET /models/{version} com sucesso."""
        mock_model_repo.get_model_version = AsyncMock(
            return_value={"version": "v8", "stage": "production", "f1_score": 0.73}
        )

        response = client.get("/api/v1/ml/models/v8")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "v8"
        assert data["f1_score"] == 0.73

    def test_get_model_version_not_found(self, client, mock_model_repo):
        """Testa GET /models/{version} não encontrado."""
        mock_model_repo.get_model_version = AsyncMock(return_value=None)

        response = client.get("/api/v1/ml/models/v99")

        assert response.status_code == 404


class TestPromoteModel:
    """Testes POST /models/{version}/promote."""

    def test_promote_model_immediate(self, client, mock_model_repo):
        """Testa promoção imediata."""
        mock_model_repo.get_model_version = AsyncMock(
            return_value={"version": "v9", "stage": "staging"}
        )

        response = client.post("/api/v1/ml/models/v9/promote", json={"strategy": "immediate"})

        assert response.status_code == 200
        mock_model_repo.promote_model.assert_called_once()

    def test_promote_model_canary(self, client, mock_model_repo):
        """Testa promoção canary."""
        mock_model_repo.get_model_version = AsyncMock(
            return_value={"version": "v9", "stage": "staging"}
        )
        # Mock para retornar modelo atual de produção
        mock_model_repo.list_models = AsyncMock(
            return_value=[{"version": "v8", "stage": "production", "is_active": True}]
        )
        mock_model_repo.promote_model = AsyncMock(return_value=True)

        response = client.post("/api/v1/ml/models/v9/promote", json={"strategy": "canary"})

        assert response.status_code == 200

    def test_promote_model_not_in_staging(self, client, mock_model_repo):
        """Testa promoção de modelo não em staging."""
        mock_model_repo.get_model_version = AsyncMock(
            return_value={"version": "v9", "stage": "archived"}
        )

        response = client.post("/api/v1/ml/models/v9/promote", json={"strategy": "immediate"})

        assert response.status_code == 400


class TestGetDrift:
    """Testes GET /drift."""

    def test_get_drift_metrics(self, client, mock_drift_detector):
        """Testa GET /drift."""
        mock_drift_detector.detect_drift = AsyncMock(
            return_value={"model_version": "v8", "drift_detected": False, "alerts": []}
        )

        response = client.get("/api/v1/ml/drift")

        assert response.status_code == 200
        data = response.json()
        assert "model_version" in data
        assert "drift_detected" in data

    def test_get_drift_with_window(self, client, mock_drift_detector):
        """Testa GET /drift com window parameter."""
        response = client.get("/api/v1/ml/drift?window=48")

        assert response.status_code == 200


class TestGetMetrics:
    """Testes GET /metrics (Prometheus)."""

    def test_get_metrics_prometheus(self, client):
        """Testa GET /metrics em formato Prometheus."""
        response = client.get("/api/v1/ml/metrics")

        assert response.status_code == 200
        # Verifica que retorna texto plano
        assert "ml_approval_model_version" in response.text


@pytest.mark.skip(
    reason="Endpoint DELETE /models/{version} não implementado ainda - funcionalidade futura"
)
class TestDeleteModel:
    """Testes DELETE /models/{version}."""

    def test_delete_model_success(self, client, mock_model_repo):
        """Testa DELETE /models/{version} com sucesso."""
        mock_model_repo.get_model_version = AsyncMock(
            return_value={"version": "v7", "stage": "archived"}
        )
        mock_model_repo.delete_model = AsyncMock(return_value=True)

        response = client.delete("/api/v1/ml/models/v7")

        assert response.status_code == 204

    def test_delete_model_in_production(self, client, mock_model_repo):
        """Testa DELETE /models/{version} em production (deve falhar)."""
        mock_model_repo.get_model_version = AsyncMock(
            return_value={"version": "v8", "stage": "production", "is_active": True}
        )

        response = client.delete("/api/v1/ml/models/v8")

        assert response.status_code == 400


@pytest.mark.skip(
    reason="Endpoint POST /models/{version}/rollback não implementado ainda - funcionalidade futura"
)
class TestRollbackModel:
    """Testes POST /models/{version}/rollback."""

    def test_rollback_to_previous_version(self, client, mock_model_repo):
        """Testa rollback para versão anterior."""
        mock_model_repo.get_model_version = AsyncMock(
            return_value={"version": "v7", "stage": "production"}
        )
        mock_model_repo.list_models = AsyncMock(
            return_value=[{"version": "v8", "stage": "production", "is_active": True}]
        )
        mock_model_repo.promote_model = AsyncMock(return_value=True)

        response = client.post("/api/v1/ml/models/v7/rollback")

        assert response.status_code == 200

    def test_rollback_model_not_found(self, client, mock_model_repo):
        """Testa rollback para modelo inexistente."""
        mock_model_repo.get_model_version = AsyncMock(return_value=None)

        response = client.post("/api/v1/ml/models/v99/rollback")

        assert response.status_code == 404


@pytest.mark.skip(
    reason="Endpoint GET /models/{version}/stats não implementado ainda - funcionalidade futura"
)
class TestGetModelStats:
    """Testes GET /models/{version}/stats."""

    def test_get_model_stats_success(self, client, mock_model_repo):
        """Testa GET /models/{version}/stats com sucesso."""
        mock_model_repo.get_model_stats = AsyncMock(
            return_value={
                "version": "v8",
                "total_predictions": 10000,
                "correct_predictions": 8000,
                "accuracy": 0.80,
                "f1_score": 0.73,
                "precision": 0.75,
                "recall": 0.71,
            }
        )

        response = client.get("/api/v1/ml/models/v8/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "v8"
        assert data["accuracy"] == 0.80

    def test_get_model_stats_not_found(self, client, mock_model_repo):
        """Testa GET /models/{version}/stats para modelo inexistente."""
        mock_model_repo.get_model_stats = AsyncMock(return_value=None)

        response = client.get("/api/v1/ml/models/v99/stats")

        assert response.status_code == 404


@pytest.mark.skip(
    reason="Endpoint GET /models/compare não implementado ainda - funcionalidade futura"
)
class TestModelComparison:
    """Testes GET /models/compare."""

    def test_compare_two_models(self, client, mock_model_repo):
        """Testa comparação entre dois modelos."""
        mock_model_repo.compare_models = AsyncMock(
            return_value={
                "v8": {"f1_score": 0.73, "accuracy": 0.80},
                "v9": {"f1_score": 0.75, "accuracy": 0.82},
                "improvement": {"f1_score": 0.02, "accuracy": 0.02},
            }
        )

        response = client.get("/api/v1/ml/models/compare?v1=v8&v2=v9")

        assert response.status_code == 200
        data = response.json()
        assert "v8" in data
        assert "v9" in data
        assert "improvement" in data

    def test_compare_models_missing_params(self, client):
        """Testa comparação sem parâmetros obrigatórios."""
        response = client.get("/api/v1/ml/models/compare?v1=v8")

        assert response.status_code == 400
