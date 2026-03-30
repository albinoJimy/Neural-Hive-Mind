"""Testes da API de otimizações."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from src.main import app


@pytest.fixture
def mock_repository():
    """Mock do repository de otimizações."""
    repo = AsyncMock()

    # Dado de teste padrão
    test_recommendation = {
        "id": "test-001",
        "ticket_id": "TICKET-001",
        "workflow_id": "workflow-001",
        "status": "approved",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "performance_analysis": {"total_duration_ms": 5000, "peak_memory_mb": 128},
        "recommendations": [
            {
                "id": "rec-001",
                "type": "reduce_complexity",
                "severity": "high",
                "description": "Função complexa",
                "target_type": "code",
            }
        ],
    }

    repo.list_by_filters.return_value = {
        "total": 1,
        "offset": 0,
        "limit": 50,
        "items": [test_recommendation]
    }

    # get_by_id retorna o dado se for test-001, None caso contrário
    async def mock_get_by_id(rec_id):
        if rec_id == "test-001":
            return test_recommendation.copy()
        return None

    repo.get_by_id.side_effect = mock_get_by_id
    repo.update_status.return_value = True
    repo.get_metrics.return_value = {
        "total": 10,
        "by_status": {"pending": 3, "approved": 2, "applied": 4, "rejected": 1},
        "avg_improvement_pct": 15.5,
        "total_time_saved_ms": 50000,
        "best_improvement_pct": 35.2,
    }
    repo.get_dashboard_data.return_value = {
        "total_recommendations": 10,
        "pending_approval": 3,
        "applied": 4,
        "avg_improvement_pct": 15.5,
        "top_issue_types": [
            {"type": "high_complexity", "count": 5},
            {"type": "slow_query", "count": 3}
        ],
        "recent_recommendations": []
    }
    repo.get_timeline.return_value = []
    return repo


@pytest.fixture
def client(mock_repository):
    """Cliente de teste com repository mockado."""
    app.dependency_overrides = {}

    async def override_get_repo():
        return mock_repository

    from src.api.optimizations import get_optimization_repository
    app.dependency_overrides[get_optimization_repository] = override_get_repo

    yield TestClient(app)

    app.dependency_overrides = {}


class TestOptimizationsAPI:
    """Testes da API de otimizações."""

    def test_list_recommendations(self, client):
        """Testa listagem de recomendações."""
        response = client.get("/api/v1/optimizations/recommendations")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data

    def test_get_recommendation(self, client):
        """Testa obter recomendação específica."""
        response = client.get("/api/v1/optimizations/recommendations/test-001")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-001"

    def test_get_recommendation_not_found(self, client):
        """Testa 404 para recomendação inexistente."""
        response = client.get("/api/v1/optimizations/recommendations/not-found")
        assert response.status_code == 404

    def test_approve_recommendation(self, client):
        """Testa aprovação de recomendação."""
        response = client.post(
            "/api/v1/optimizations/recommendations/test-001/approve",
            json={"recommendation_ids": ["rec-001"], "approved_by": "test@example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"

    def test_apply_recommendation(self, client, mock_repository):
        """Testa aplicação de otimização."""
        # Garantir que o status da recomendação é approved
        async def mock_get_by_id_approved(rec_id):
            if rec_id == "test-001":
                rec = {
                    "id": "test-001",
                    "ticket_id": "TICKET-001",
                    "workflow_id": "workflow-001",
                    "status": "approved",  # Precisa estar approved para apply
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "performance_analysis": {"total_duration_ms": 5000, "peak_memory_mb": 128},
                    "recommendations": [{"id": "rec-001"}],
                }
                return rec
            return None

        mock_repository.get_by_id.side_effect = mock_get_by_id_approved

        response = client.post(
            "/api/v1/optimizations/recommendations/test-001/apply",
            json={"recommendation_ids": ["rec-001"], "validate": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "applied"

    def test_metrics(self, client):
        """Testa endpoint de métricas."""
        response = client.get("/api/v1/optimizations/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "performance" in data
        # Verificar que os novos campos estão presentes
        assert "total_time_saved_ms" in data["performance"]
        assert "best_improvement_pct" in data["performance"]
        assert "top_issues" in data

    def test_dashboard(self, client):
        """Testa endpoint de dashboard."""
        response = client.get("/api/v1/optimizations/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "total_recommendations" in data

    def test_timeline(self, client):
        """Testa timeline por workflow."""
        response = client.get("/api/v1/optimizations/timeline/workflow-001")
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "workflow-001"
        assert "optimizations" in data
