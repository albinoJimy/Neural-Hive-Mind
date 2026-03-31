"""
Fixtures para testes E2E de Vault e SPIFFE.

Estes fixtures são usados pelos testes de integração que requerem
um ambiente real de Vault e SPIFFE (controlado pela variável RUN_VAULT_SPIFFE_E2E).
"""
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.config.settings import OrchestratorSettings
from src.clients.vault_integration import OrchestratorVaultClient

# Verificar se devemos rodar testes E2E reais
REAL_E2E = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"


def require_real_env():
    """Levanta exceção se não estiver em ambiente E2E real."""
    if not REAL_E2E:
        pytest.skip("RUN_VAULT_SPIFFE_E2E not enabled")


@pytest.fixture
async def vault_client():
    """
    Cliente Vault para testes E2E.

    Retorna um mock quando RUN_VAULT_SPIFFE_E2E não está ativo.
    """
    # Mock para testes unitários (E2E real não implementado ainda)
    client = MagicMock()
    client.token = "mock_token"
    client.token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    client.get_database_credentials = AsyncMock(return_value={
        "username": "mock_user",
        "password": "mock_pass",
        "ttl": 3600
    })
    client.renew_token = AsyncMock(return_value=True)
    yield client


@pytest.fixture
async def spiffe_manager():
    """
    SPIFFE manager para testes E2E.

    Retorna um mock (E2E real não implementado ainda).
    """
    manager = MagicMock()
    manager.initialize = AsyncMock()
    manager.close = AsyncMock()
    manager.fetch_jwt_svid = AsyncMock(return_value=MagicMock(
        token="mock_jwt_token",
        spiffe_id="spiffe://neural-hive.local/test"
    ))
    yield manager


@pytest.fixture
async def orchestrator_vault_client():
    """
    Cliente Vault do Orchestrator para testes E2E.

    Mock configurado com fallback (E2E real não implementado ainda).
    """
    settings = build_test_settings()
    client = OrchestratorVaultClient(settings)
    client.vault_client = None  # Simula Vault indisponível
    yield client


@pytest.fixture
def build_test_settings():
    """
    Constrói configurações de teste para Orchestrator.

    Usa variáveis de ambiente quando disponíveis, senão usa defaults.
    """
    settings = OrchestratorSettings()

    # Override com variáveis de ambiente ou defaults de teste
    settings.vault_address = os.getenv("VAULT_ADDR", "http://localhost:8200")
    settings.vault_role = os.getenv("VAULT_ROLE", "orchestrator")
    settings.vault_auth_path = os.getenv("VAULT_AUTH_PATH", "kubernetes")
    settings.vault_fail_open = True
    settings.vault_token_ttl_seconds = 3600

    # Credenciais de fallback
    settings.postgres_user = os.getenv("POSTGRES_USER", "test_user")
    settings.postgres_password = os.getenv("POSTGRES_PASSWORD", "test_pass")
    settings.mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/test")
    settings.redis_password = os.getenv("REDIS_PASSWORD", "test_redis_pass")

    # Kafka credentials
    settings.kafka_username = os.getenv("KAFKA_USERNAME", "test_kafka_user")
    settings.kafka_password = os.getenv("KAFKA_PASSWORD", "test_kafka_pass")

    return settings
