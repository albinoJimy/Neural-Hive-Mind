"""Testes de integração para endpoint /metrics.

Autor: Neural Hive Mind
Criado: 2026-04-19 (REFACTOR-H-007)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.metrics import (
    increment_cdc_events,
    set_cdc_consumer_lag,
    set_migration_progress,
)


@pytest.mark.asyncio
async def test_metrics_endpoint_response():
    """Testa que /metrics retorna conteúdo Prometheus."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_metrics_contains_cdc_events():
    """Testa que métricas CDC aparecem no output."""
    # Primeiro incrementar algumas métricas
    increment_cdc_events(job_id="test-job-1", operation_type="insert")
    increment_cdc_events(job_id="test-job-1", operation_type="update")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

        assert response.status_code == 200
        content = response.text

        # Verificar que as métricas aparecem
        assert "data_migration_cdc_events_processed" in content
        assert 'job_id="test-job-1"' in content


@pytest.mark.asyncio
async def test_metrics_contains_migration_progress():
    """Testa que progresso de migração aparece no output."""
    set_migration_progress(job_id="test-job-2", progress=45.5)
    set_cdc_consumer_lag(job_id="test-job-2", lag_ms=1234)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

        assert response.status_code == 200
        content = response.text

        assert "data_migration_migration_progress_percentage" in content
        assert 'job_id="test-job-2"' in content
        assert "data_migration_cdc_consumer_lag_ms" in content


@pytest.mark.asyncio
async def test_metrics_endpoint_content_type():
    """Testa que content-type está correto."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

        assert response.status_code == 200
        # Prometheus usa text/plain versão 0.0.4
        assert "text/plain" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_metrics_has_help_and_type():
    """Testa que métricas têm metadados HELP e TYPE."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

        content = response.text

        # Prometheus deve incluir HELP e TYPE para cada métrica
        assert "# HELP" in content
        assert "# TYPE" in content


@pytest.mark.asyncio
async def test_metrics_multiple_jobs():
    """Testa que métricas de múltiplos jobs aparecem."""
    jobs = ["job-1", "job-2", "job-3"]

    for job in jobs:
        set_migration_progress(job_id=job, progress=50.0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

        assert response.status_code == 200
        content = response.text

        # Todos os jobs devem aparecer
        for job in jobs:
            assert f'job_id="{job}"' in content
