"""Testes de integração para pause/resume de migrações."""

import pytest
from httpx import AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_pause_migration():
    """Testa pausar uma migração em andamento."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Criar job de migração
        response = await client.post(
            "/api/v1/migrations/jobs",
            json={
                "source_db": {"type": "postgresql", "host": "localhost", "database": "test"},
                "target_db": {"type": "mongodb", "connection_string": "mongodb://localhost"},
            },
        )
        job_id = response.json()["job_id"]

        # Pausar migração
        response = await client.post(f"/api/v1/migrations/jobs/{job_id}/pause")
        assert response.status_code == 200
        assert response.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_resume_migration():
    """Testa retomar uma migração pausada."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Criar e pausar job
        response = await client.post(
            "/api/v1/migrations/jobs",
            json={
                "source_db": {"type": "postgresql", "host": "localhost", "database": "test"},
                "target_db": {"type": "mongodb", "connection_string": "mongodb://localhost"},
            },
        )
        job_id = response.json()["job_id"]
        await client.post(f"/api/v1/migrations/jobs/{job_id}/pause")

        # Retomar migração
        response = await client.post(f"/api/v1/migrations/jobs/{job_id}/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "running"
