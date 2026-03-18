"""Testes da API de otimizações."""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from src.main import app
from src.api.optimizations import _recommendations_store


@pytest.fixture
def client():
    """Cliente de teste."""
    # Adicionar dado de teste
    _recommendations_store.append({
        "id": "test-001",
        "ticket_id": "TICKET-001",
        "workflow_id": "workflow-001",
        "status": "pending",
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
    })

    yield TestClient(app)

    # Limpar após teste
    _recommendations_store.clear()


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

    def test_apply_recommendation(self, client):
        """Testa aplicação de otimização."""
        # Primeiro aprovar
        client.post(
            "/api/v1/optimizations/recommendations/test-001/approve",
            json={"recommendation_ids": ["rec-001"], "approved_by": "test@example.com"}
        )

        # Depois aplicar
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
