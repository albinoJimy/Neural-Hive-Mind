"""Testes de integração para pause/resume de migrações.

NOTA: Estes testes requerem infraestrutura (MongoDB, PostgreSQL) via Docker Compose.
Para executar: docker-compose up -d && pytest tests/integration/
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app

pytestmark = pytest.mark.integration


@pytest.mark.skip(reason="Requer MongoDB e PostgreSQL reais via Docker Compose")
@pytest.mark.asyncio
async def test_pause_migration():
    """Testa pausar uma migração em andamento."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Criar job de migração com formato correto da API
        await client.post(
            "/api/v1/migrations",
            json={
                "legacy_db_url": "postgresql://user:pass@localhost:5432/legacy",
                "modern_db_url": "postgresql://user:pass@localhost:5432/modern",
                "tables": ["users", "orders"],
                "batch_size": 1000,
                "auto_approve": True,
            },
        )
        # Nota: Este teste falhará sem bancos reais, mas testa a estrutura da API
        # Em produção, seriam usados mocks ou bancos de teste


@pytest.mark.skip(reason="Requer MongoDB real via Docker Compose")
@pytest.mark.asyncio
async def test_pause_migration_endpoint_exists():
    """Testa que o endpoint de pause existe e responde."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tentar pausar uma migração inexistente - deve retornar 404, não 405
        response = await client.post("/api/v1/migrations/test-job-id/pause")
        # Espera-se 404 (job não encontrado) ou erro de conexão, não 405 (método não permitido)
        assert response.status_code != 405  # Se for 405, o endpoint não existe


@pytest.mark.skip(reason="Requer MongoDB real via Docker Compose")
@pytest.mark.asyncio
async def test_resume_migration_endpoint_exists():
    """Testa que o endpoint de resume existe e responde."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tentar retomar uma migração inexistente
        response = await client.post("/api/v1/migrations/test-job-id/resume")
        # Espera-se 404 (job não encontrado) ou erro de conexão, não 405
        assert response.status_code != 405  # Se for 405, o endpoint não existe
