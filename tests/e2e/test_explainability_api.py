"""
E2E Tests para Explainability API

Testes de integração para a API de explicabilidade do Neural Hive-Mind.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from httpx import AsyncClient
from pymongo import MongoClient


@pytest.fixture(scope="module")
def explainability_token():
    """Cria uma entrada de explicabilidade de teste no MongoDB."""
    client = MongoClient("mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin")
    db = client["neural_hive"]

    # Criar entrada de teste
    test_entry = {
        "explainability_token": "test_token_e2e_001",
        "plan_id": "test_plan_001",
        "decision_id": "test_decision_001",
        "specialist_id": "technical",
        "method": "rule_based",
        "explanation": {
            "reasoning": "Test explanation for E2E",
            "factors": [
                {"name": "test_factor", "value": 0.8, "weight": 0.5}
            ],
            "confidence": 0.85
        },
        "generated_at": datetime.now(timezone.utc)
    }

    db.explainability_ledger.insert_one(test_entry)

    yield test_entry["explainability_token"]

    # Cleanup
    db.explainability_ledger.delete_one({"explainability_token": test_entry["explainability_token"]})


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_explainability_health_check():
    """Testa health check da API."""
    async with AsyncClient(base_url="http://explainability-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "explainability-api"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_explainability_readiness_check():
    """Testa readiness check da API."""
    async with AsyncClient(base_url="http://explainability-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "mongodb" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_explainability_by_token(explainability_token):
    """Testa consulta de explicação por token."""
    async with AsyncClient(base_url="http://explainability-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get(f"/api/v1/explainability/{explainability_token}")

        assert response.status_code == 200
        data = response.json()
        assert data["explainability_token"] == explainability_token
        assert "explanation" in data
        assert "method" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_explainability_by_plan():
    """Testa consulta de explicações por plan_id."""
    async with AsyncClient(base_url="http://explainability-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/api/v1/explainability/by-plan/test_plan_001")

        assert response.status_code == 200
        data = response.json()
        assert data["plan_id"] == "test_plan_001"
        assert "explanations" in data
        assert data["count"] >= 1


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_explainability_by_decision():
    """Testa consulta de explicações por decision_id."""
    async with AsyncClient(base_url="http://explainability-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/api/v1/explainability/by-decision/test_decision_001")

        assert response.status_code == 200
        data = response.json()
        assert data["decision_id"] == "test_decision_001"
        assert "explanations" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_explainability_stats():
    """Testa consulta de estatísticas de explicabilidade."""
    async with AsyncClient(base_url="http://explainability-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/api/v1/explainability/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_explanations" in data
        assert "by_method" in data
        assert isinstance(data["total_explanations"], int)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_explainability_404_for_invalid_token():
    """Testa 404 para token inexistente."""
    async with AsyncClient(base_url="http://explainability-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/api/v1/explainability/invalid_token_xyz")

        assert response.status_code == 404


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_explainability_metrics_endpoint():
    """Testa endpoint de métricas Prometheus."""
    async with AsyncClient(base_url="http://explainability-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/metrics")

        assert response.status_code == 200
        # Métricas Prometheus retornam texto
        assert "neural_hive_explainability_queries_total" in response.text
