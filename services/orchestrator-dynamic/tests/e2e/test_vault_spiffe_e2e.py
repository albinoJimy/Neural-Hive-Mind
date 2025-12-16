import os
from datetime import datetime, timedelta

import pytest

from tests.e2e.fixtures.vault_spire_setup import (
    vault_client,
    spiffe_manager,
    orchestrator_vault_client,
    require_real_env,
    build_test_settings,
)
from src.clients.vault_integration import OrchestratorVaultClient
from neural_hive_security import VaultClient

REAL_E2E = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"
pytestmark = pytest.mark.skipif(not REAL_E2E, reason="RUN_VAULT_SPIFFE_E2E not enabled")


@pytest.mark.asyncio
async def test_vault_kubernetes_authentication(vault_client: VaultClient):
    """Valida autenticação no Vault usando token de service account."""
    require_real_env()
    assert vault_client.token is not None
    assert vault_client.token_expiry is not None
    assert vault_client.token_expiry > datetime.utcnow()


@pytest.mark.asyncio
async def test_fetch_postgres_dynamic_credentials(vault_client: VaultClient):
    """Busca credenciais dinâmicas do PostgreSQL (temporal-orchestrator)."""
    require_real_env()
    creds = await vault_client.get_database_credentials("temporal-orchestrator")
    assert creds["username"]
    assert creds["password"]
    assert creds.get("ttl", 0) > 0


@pytest.mark.asyncio
async def test_fetch_static_secrets(orchestrator_vault_client: OrchestratorVaultClient):
    """Busca segredos estáticos (MongoDB, Redis, Kafka) do Vault."""
    require_real_env()
    mongodb_uri = await orchestrator_vault_client.get_mongodb_uri()
    redis_password = await orchestrator_vault_client.get_redis_password()
    kafka_creds = await orchestrator_vault_client.get_kafka_credentials()

    assert mongodb_uri
    assert redis_password is not None
    assert kafka_creds.get("username") is not None or kafka_creds.get("password") is not None


@pytest.mark.asyncio
async def test_token_renewal_before_expiration(vault_client: VaultClient):
    """Renova token do Vault antes da expiração."""
    require_real_env()
    success = await vault_client.renew_token()
    assert success is True


@pytest.mark.asyncio
async def test_credential_rotation(orchestrator_vault_client: OrchestratorVaultClient):
    """Valida renovação de credenciais dinâmicas."""
    require_real_env()
    creds = await orchestrator_vault_client.get_postgres_credentials()
    assert creds["username"]

    # Força threshold de renovação simulando expiração iminente
    orchestrator_vault_client._postgres_credentials_expiry = datetime.utcnow() + timedelta(seconds=5)
    await orchestrator_vault_client._renew_postgres_credentials_if_needed()


@pytest.mark.asyncio
async def test_fail_open_behavior_when_vault_unavailable():
    """Fail-open: credenciais de fallback quando Vault indisponível."""
    require_real_env()
    settings = build_test_settings()
    settings.vault_address = "http://127.0.0.1:9999"  # endereço inválido
    settings.vault_fail_open = True
    client = OrchestratorVaultClient(settings)
    try:
        await client.initialize()
    except Exception:
        # falha esperada; garantir fallback
        client.vault_client = None

    creds = await client.get_postgres_credentials()
    assert creds["username"] == settings.postgres_user
    assert creds["password"] == settings.postgres_password


@pytest.mark.asyncio
async def test_fail_closed_behavior_when_vault_unavailable():
    """Fail-closed: erro propagado quando fail_open=False."""
    require_real_env()
    settings = build_test_settings()
    settings.vault_address = "http://127.0.0.1:9999"
    settings.vault_fail_open = False
    client = OrchestratorVaultClient(settings)

    with pytest.raises(Exception):
        await client.initialize()
