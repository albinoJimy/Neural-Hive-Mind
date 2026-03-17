"""
E2E Tests para Memory Layer API

Testes de integração para a API de memória unificada do Neural Hive-Mind.
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_memory_layer_health_check():
    """Testa health check da API."""
    async with AsyncClient(base_url="http://memory-layer-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "memory-layer-api"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_memory_layer_readiness_check():
    """Testa readiness check da API."""
    async with AsyncClient(base_url="http://memory-layer-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_memory_query_basic():
    """Testa consulta básica de memória."""
    async with AsyncClient(base_url="http://memory-layer-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        query_request = {
            "query_type": "semantic",
            "query": "test query",
            "filters": {
                "agent_id": "test_agent",
                "time_range_hours": 24
            },
            "limit": 10
        }

        response = await client.post("/api/v1/memory/query", json=query_request)

        # Pode retornar 200 com resultados ou 404 se não houver dados
        assert response.status_code in [200, 404]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_memory_lineage_endpoint():
    """Testa consulta de linhagem de memória."""
    async with AsyncClient(base_url="http://memory-layer-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        # Usar um entity_id de teste
        response = await client.get("/api/v1/memory/lineage/test_entity_001")

        # Pode retornar 200 com linhagem ou 404 se não existir
        assert response.status_code in [200, 404]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_memory_quality_stats():
    """Testa consulta de estatísticas de qualidade de dados."""
    async with AsyncClient(base_url="http://memory-layer-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/api/v1/memory/quality/stats")

        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_memory_catalog_assets():
    """Testa catálogo de ativos de memória."""
    async with AsyncClient(base_url="http://memory-layer-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/api/v1/memory/catalog/assets")

        assert response.status_code == 200
        data = response.json()
        assert "assets" in data or isinstance(data, list)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_memory_invalidate():
    """Testa invalidação de cache de memória."""
    async with AsyncClient(base_url="http://memory-layer-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        invalidate_request = {
            "keys": ["test_key_001"],
            "pattern": None
        }

        response = await client.post("/api/v1/memory/invalidate", json=invalidate_request)

        assert response.status_code == 200
        data = response.json()
        assert "invalidated_keys" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_memory_metrics_endpoint():
    """Testa endpoint de métricas Prometheus."""
    async with AsyncClient(base_url="http://memory-layer-api.neural-hive.svc.cluster.local:8000", timeout=30.0) as client:
        response = await client.get("/metrics")

        assert response.status_code == 200
        # Métricas Prometheus retornam texto
        assert "python_info" in response.text or "HELP" in response.text
