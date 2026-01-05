"""Testes E2E para APIs do Optimizer Agents."""

import pytest
import httpx
import os


# URL base configurável via variável de ambiente
OPTIMIZER_BASE_URL = os.getenv('OPTIMIZER_BASE_URL', 'http://optimizer-agents:8000')


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_optimizer_optimizations_list_e2e():
    """Teste E2E: listar otimizações."""
    async with httpx.AsyncClient(base_url=OPTIMIZER_BASE_URL, timeout=30.0) as client:
        response = await client.get('/api/v1/optimizations')
        assert response.status_code == 200
        data = response.json()
        assert 'optimizations' in data
        assert 'total' in data
        assert 'page' in data
        assert 'page_size' in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_optimizer_optimizations_statistics_e2e():
    """Teste E2E: estatísticas de otimizações."""
    async with httpx.AsyncClient(base_url=OPTIMIZER_BASE_URL, timeout=30.0) as client:
        response = await client.get('/api/v1/optimizations/statistics/summary')
        assert response.status_code == 200
        data = response.json()
        assert 'total_optimizations' in data
        assert 'success_rate' in data
        assert 'average_improvement' in data
        assert 'by_type' in data
        assert 'by_component' in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_optimizer_experiments_list_e2e():
    """Teste E2E: listar experimentos."""
    async with httpx.AsyncClient(base_url=OPTIMIZER_BASE_URL, timeout=30.0) as client:
        response = await client.get('/api/v1/experiments')
        assert response.status_code == 200
        data = response.json()
        assert 'experiments' in data
        assert 'total' in data
        assert 'page' in data
        assert 'page_size' in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_optimizer_experiments_statistics_e2e():
    """Teste E2E: estatísticas de experimentos."""
    async with httpx.AsyncClient(base_url=OPTIMIZER_BASE_URL, timeout=30.0) as client:
        response = await client.get('/api/v1/experiments/statistics/summary')
        assert response.status_code == 200
        data = response.json()
        assert 'total_experiments' in data
        assert 'by_status' in data
        assert 'by_type' in data
        assert 'average_duration_seconds' in data
        assert 'success_rate' in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_optimizer_health_check_e2e():
    """Teste E2E: health check do serviço."""
    async with httpx.AsyncClient(base_url=OPTIMIZER_BASE_URL, timeout=30.0) as client:
        response = await client.get('/health')
        assert response.status_code == 200


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_optimizer_openapi_docs_e2e():
    """Teste E2E: documentação OpenAPI disponível."""
    async with httpx.AsyncClient(base_url=OPTIMIZER_BASE_URL, timeout=30.0) as client:
        response = await client.get('/openapi.json')
        assert response.status_code == 200
        data = response.json()
        assert 'openapi' in data
        assert 'paths' in data
        # Validar que os endpoints estão documentados
        assert '/api/v1/optimizations' in data['paths']
        assert '/api/v1/experiments' in data['paths']
