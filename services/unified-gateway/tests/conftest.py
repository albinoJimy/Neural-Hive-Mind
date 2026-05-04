"""Configuração compartilhada para testes."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.fixture
def client() -> TestClient:
    """Cliente HTTP síncrono para testes."""
    from src.main import app

    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncClient:
    """Cliente HTTP assíncrono para testes."""
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_jwt_token():
    """Cria um JWT token de teste."""
    import jwt

    payload = {
        "sub": "test-user-123",
        "tenant_id": "test-tenant-456",
        "session_id": "test-session-789",
        "roles": ["user"],
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")
