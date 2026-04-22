"""Testes unitários para os roteadores da API."""

from unittest.mock import AsyncMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture()
def client():
    """Cliente de teste FastAPI."""
    return TestClient(app)


@pytest.fixture()
def mock_pipeline_repo():
    """Mock do PipelineRunRepository."""
    from src.repositories.pipeline_repository import PipelineRunRepository

    repo = PipelineRunRepository()

    # Mock dos métodos
    repo.create = AsyncMock(return_value="test-run-id")
    repo.find_by_id = AsyncMock(
        return_value={
            "_id": "test-run-id",
            "run_id": "test-run-id",
            "manifest_id": "manifest-1",
            "repo_url": "https://github.com/org/repo",
            "git_sha": "abc123",
            "status": "pending",
            "current_stage": None,
            "stages_completed": [],
            "stages_failed": [],
            "started_at": "2026-03-27T10:00:00Z",
            "finished_at": None,
            "duration_seconds": None,
            "logs_url": None,
        }
    )
    repo.find_many = AsyncMock(return_value=[])
    repo.count = AsyncMock(return_value=0)
    repo.find_recent_by_repo = AsyncMock(return_value=[])
    repo.find_by_date_range = AsyncMock(return_value=[])
    repo.update = AsyncMock(return_value=True)
    repo.delete = AsyncMock(return_value=True)
    repo.get_success_rate = AsyncMock(return_value=0.85)
    repo.aggregate = AsyncMock(return_value=[])

    return repo


@pytest.fixture()
def mock_anomaly_repo():
    """Mock do AnomalyRepository."""
    from src.repositories.pipeline_repository import AnomalyRepository

    repo = AnomalyRepository()

    repo.find_by_id = AsyncMock(
        return_value={
            "_id": "anom-1",
            "anomaly_id": "anom-1",
            "repo_url": "https://github.com/org/repo",
            "type": "flaky_test",
            "severity": "medium",
            "description": "Test is flaky",
            "resolved": False,
            "detected_at": "2026-03-27T10:00:00Z",
            "resolved_at": None,
            "run_id": None,
            "affected_component": "test_login",
        }
    )
    repo.find_many = AsyncMock(return_value=[])
    repo.find_unresolved = AsyncMock(return_value=[])
    repo.find_by_type = AsyncMock(return_value=[])
    repo.mark_resolved = AsyncMock(return_value=True)
    repo.delete = AsyncMock(return_value=True)

    return repo


@pytest.fixture()
def mock_manifest_repo():
    """Mock do PipelineManifestRepository."""
    from src.repositories.pipeline_repository import PipelineManifestRepository

    repo = PipelineManifestRepository()

    repo.create = AsyncMock(return_value="manifest-id")
    repo.find_by_repo = AsyncMock(return_value=None)
    repo.find_by_id = AsyncMock(return_value=None)
    repo.update = AsyncMock(return_value=True)
    repo.delete = AsyncMock(return_value=True)

    return repo


class TestHealthRouter:
    """Testes do router de health."""

    def test_health_check(self, client):
        """Testa health check básico."""
        response = client.get("/api/v1/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data

    def test_status_endpoint(self, client):
        """Testa endpoint de status detalhado."""
        response = client.get("/api/v1/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "api" in data["components"]

    def test_ping(self, client):
        """Testa endpoint ping."""
        response = client.get("/api/v1/ping")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"ping": "pong"}


class TestPipelineRunsRouter:
    """Testes do router de execuções de pipeline."""

    def test_list_runs_empty(self, client, mock_pipeline_repo, monkeypatch):
        """Testa listagem de runs vazia."""

        monkeypatch.setattr("src.api.routers.pipeline_runs.repo", mock_pipeline_repo)

        response = client.get("/api/v1/pipelines/runs")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_create_run(self, client, mock_pipeline_repo, monkeypatch):
        """Testa criação de run."""

        monkeypatch.setattr("src.api.routers.pipeline_runs.repo", mock_pipeline_repo)

        payload = {
            "manifest_id": "manifest-1",
            "repo_url": "https://github.com/org/repo",
            "git_sha": "abc123",
        }

        response = client.post("/api/v1/pipelines/runs", json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["manifest_id"] == "manifest-1"
        assert data["repo_url"] == "https://github.com/org/repo"
        assert data["git_sha"] == "abc123"

    def test_get_run(self, client, mock_pipeline_repo, monkeypatch):
        """Testa obter run específica."""

        monkeypatch.setattr("src.api.routers.pipeline_runs.repo", mock_pipeline_repo)

        response = client.get("/api/v1/pipelines/runs/test-run-id")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["run_id"] == "test-run-id"
        assert data["repo_url"] == "https://github.com/org/repo"

    def test_get_run_not_found(self, client, mock_pipeline_repo, monkeypatch):
        """Testa obter run inexistente."""

        mock_pipeline_repo.find_by_id = AsyncMock(return_value=None)
        monkeypatch.setattr("src.api.routers.pipeline_runs.repo", mock_pipeline_repo)

        response = client.get("/api/v1/pipelines/runs/non-existent")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_run(self, client, mock_pipeline_repo, monkeypatch):
        """Testa deletar run."""

        monkeypatch.setattr("src.api.routers.pipeline_runs.repo", mock_pipeline_repo)

        response = client.delete("/api/v1/pipelines/runs/test-run-id")

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_get_repository_stats(self, client, mock_pipeline_repo, monkeypatch):
        """Testa obter estatísticas do repositório."""

        mock_pipeline_repo.aggregate = AsyncMock(
            side_effect=[
                [{"_id": "success", "count": 85}, {"_id": "failed", "count": 15}],
            ]
        )
        monkeypatch.setattr("src.api.routers.pipeline_runs.repo", mock_pipeline_repo)

        response = client.get("/api/v1/pipelines/repositories/github.com/org/repo/stats")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "success_rate" in data
        assert "total_runs" in data


class TestAnomaliesRouter:
    """Testes do router de anomalias."""

    def test_list_anomalies_empty(self, client, mock_anomaly_repo, monkeypatch):
        """Testa listagem de anomalias vazia."""

        monkeypatch.setattr("src.api.routers.anomalies.repo", mock_anomaly_repo)

        response = client.get("/api/v1/anomalies")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_get_anomaly(self, client, mock_anomaly_repo, monkeypatch):
        """Testa obter anomalia específica."""

        monkeypatch.setattr("src.api.routers.anomalies.repo", mock_anomaly_repo)

        response = client.get("/api/v1/anomalies/anom-1")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["anomaly_id"] == "anom-1"
        assert data["type"] == "flaky_test"

    def test_get_anomaly_not_found(self, client, mock_anomaly_repo, monkeypatch):
        """Testa obter anomalia inexistente."""

        mock_anomaly_repo.find_by_id = AsyncMock(return_value=None)
        monkeypatch.setattr("src.api.routers.anomalies.repo", mock_anomaly_repo)

        response = client.get("/api/v1/anomalies/non-existent")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_resolve_anomaly(self, client, mock_anomaly_repo, monkeypatch):
        """Testa resolver anomalia."""

        # Mock para retornar anomalia não resolvida primeiro
        anomaly_unresolved = {
            "_id": "anom-1",
            "anomaly_id": "anom-1",
            "resolved": False,
        }
        mock_anomaly_repo.find_by_id = AsyncMock(
            side_effect=[
                anomaly_unresolved,  # Primeira chamada (check)
                anomaly_unresolved,  # Segunda chamada (get updated)
            ]
        )
        monkeypatch.setattr("src.api.routers.anomalies.repo", mock_anomaly_repo)

        payload = {
            "resolution_notes": "Fixed by updating test",
        }

        response = client.post("/api/v1/anomalies/anom-1/resolve", json=payload)

        assert response.status_code == status.HTTP_200_OK

    def test_get_unresolved_anomalies(self, client, mock_anomaly_repo, monkeypatch):
        """Testa obter anomalias não resolvidas."""

        mock_anomaly_repo.find_unresolved = AsyncMock(
            return_value=[
                {
                    "anomaly_id": "anom-1",
                    "repo_url": "https://github.com/org/repo",
                    "type": "flaky_test",
                    "severity": "medium",
                    "description": "Test is flaky",
                    "resolved": False,
                }
            ]
        )
        monkeypatch.setattr("src.api.routers.anomalies.repo", mock_anomaly_repo)

        response = client.get("/api/v1/anomalies/repositories/github.com/org/repo/unresolved")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 1


class TestInsightsRouter:
    """Testes do router de insights."""

    def test_generate_insights(self, client, mock_pipeline_repo, monkeypatch):
        """Testa geração de insights."""
        from src.api.routers import insights

        monkeypatch.setattr(insights, "run_repo", mock_pipeline_repo)

        payload = {
            "repo_url": "https://github.com/org/repo",
            "days": 7,
        }

        response = client.post("/api/v1/insights/generate", json=payload)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "repo_url" in data
        assert "total_runs" in data

    def test_get_repository_health(
        self, client, mock_pipeline_repo, mock_anomaly_repo, monkeypatch
    ):
        """Testa obter saúde do repositório."""
        from src.api.routers import insights

        mock_pipeline_repo.get_success_rate = AsyncMock(return_value=0.9)
        mock_pipeline_repo.find_by_date_range = AsyncMock(return_value=[])

        monkeypatch.setattr(insights, "run_repo", mock_pipeline_repo)
        monkeypatch.setattr(insights, "anomaly_repo", mock_anomaly_repo)

        response = client.get("/api/v1/insights/repositories/github.com/org/repo/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "health_status" in data
        assert "success_rate" in data


class TestManifestsRouter:
    """Testes do router de manifests."""

    def test_create_manifest(self, client, mock_manifest_repo, monkeypatch):
        """Testa criação de manifesto."""
        from src.api.routers import manifests

        monkeypatch.setattr(manifests, "repo", mock_manifest_repo)

        payload = {
            "repo_url": "https://github.com/org/repo",
            "branch": "main",
            "provider": "github_actions",
            "content": "name: CI\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest",
        }

        response = client.post("/api/v1/manifests", json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["repo_url"] == "https://github.com/org/repo"
        assert data["provider"] == "github_actions"

    def test_get_manifest_not_found(self, client, mock_manifest_repo, monkeypatch):
        """Testa obter manifesto inexistente."""
        from src.api.routers import manifests

        mock_manifest_repo.find_by_repo = AsyncMock(return_value=None)
        monkeypatch.setattr(manifests, "repo", mock_manifest_repo)

        response = client.get("/api/v1/manifests/repositories/github.com/org/repo")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_manifest(self, client, mock_manifest_repo, monkeypatch):
        """Testa deletar manifesto."""
        from src.api.routers import manifests

        mock_manifest_repo.delete = AsyncMock(return_value=True)
        monkeypatch.setattr(manifests, "repo", mock_manifest_repo)

        response = client.delete("/api/v1/manifests/manifest-id")

        assert response.status_code == status.HTTP_204_NO_CONTENT
