"""
Integration tests para Health Router.

Testa endpoints de health check, readiness e liveness.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from src.api.routers.health import router as health_router, set_health_manager
from src.main import app as main_app


@pytest.fixture
def app() -> FastAPI:
    """Retorna app FastAPI para testes."""
    # Criar app minimal para testes
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(health_router)

    # Configurar health manager stub
    class StubHealthManager:
        async def check_all(self):
            return {"checks": {}}

        def get_overall_status(self):
            return "healthy"

        async def check_single(self, name):
            class Result:
                status = "healthy"

            return Result()

    set_health_manager(StubHealthManager())

    return test_app


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(app: FastAPI):
    """Testa que endpoint /health retorna 200 quando saudável."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["service_name"] == "gateway-intencoes"


@pytest.mark.asyncio
async def test_health_with_slash_returns_200(app: FastAPI):
    """Testa que endpoint /health/ com slash retorna 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready_endpoint_returns_200(app: FastAPI):
    """Testa que endpoint /health/ready retorna 200 quando pronto."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "checks" in data


@pytest.mark.asyncio
async def test_live_endpoint_returns_200(app: FastAPI):
    """Testa que endpoint /health/live retorna 200 (liveness probe)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_response_structure(app: FastAPI):
    """Testa que resposta de health tem estrutura correta."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Verificar campos obrigatórios
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "service_name" in data
        assert "neural_hive_component" in data
        assert "neural_hive_layer" in data

        # Verificar valores
        assert data["service_name"] == "gateway-intencoes"
        assert data["neural_hive_component"] == "gateway"
        assert data["neural_hive_layer"] == "experiencia"
