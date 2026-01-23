"""
Testes de integração para rotação de credenciais PostgreSQL via Vault
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Import shared module loader
from tests.integration.conftest_vault import get_vault_integration_class


@pytest.fixture
def mock_config():
    """Mock de configuração com Vault habilitado"""
    config = MagicMock()
    config.vault_enabled = True
    config.vault_address = "http://vault:8200"
    config.vault_namespace = ""
    config.vault_auth_method = "kubernetes"
    config.vault_kubernetes_role = "orchestrator-dynamic"
    config.vault_token_path = "/vault/secrets/token"
    config.vault_mount_kv = "secret"
    config.vault_mount_database = "database"
    config.vault_timeout_seconds = 5
    config.vault_max_retries = 3
    config.vault_fail_open = False
    config.vault_token_renewal_threshold = 0.2
    config.vault_db_credentials_renewal_threshold = 0.2
    config.spiffe_enabled = False
    config.postgres_host = "localhost"
    config.postgres_port = 5432
    config.postgres_database = "test"
    config.postgres_user = "static_user"
    config.postgres_password = "static_password"
    config.mongodb_uri = "mongodb://user:pass@localhost:27017"
    config.kafka_sasl_username = "kafka_user"
    config.kafka_sasl_password = "kafka_pass"
    return config


@pytest.fixture
def mock_vault_client():
    """Mock do VaultClient interno"""
    vault_client = AsyncMock()
    vault_client.initialize = AsyncMock()
    vault_client.get_database_credentials = AsyncMock()
    vault_client.read_secret = AsyncMock()
    vault_client.health_check = AsyncMock(return_value=True)
    vault_client.close = AsyncMock()
    return vault_client


@pytest.mark.asyncio
async def test_postgres_credentials_renewal_at_threshold(mock_config, mock_vault_client):
    """
    Testa renovação automática de credenciais PostgreSQL quando threshold atingido
    """
    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    # Configure mock responses
    mock_vault_client.get_database_credentials.side_effect = [
        # Primeira chamada: credenciais iniciais com TTL 100s
        {"username": "user1", "password": "pass1", "ttl": 100},
        # Segunda chamada: credenciais renovadas com TTL 100s
        {"username": "user2", "password": "pass2", "ttl": 100}
    ]

    # Buscar credenciais iniciais
    initial_creds = await vault_integration.get_postgres_credentials()
    assert initial_creds["username"] == "user1"
    assert vault_integration._postgres_credentials_expiry is not None

    # Simular passagem de tempo (81% do TTL consumido)
    vault_integration._postgres_credentials_expiry = datetime.utcnow() + timedelta(seconds=19)

    # Chamar renovação
    await vault_integration._renew_postgres_credentials_if_needed()

    # Verificar que credenciais foram renovadas
    assert vault_integration._postgres_credentials["username"] == "user2"
    assert mock_vault_client.get_database_credentials.call_count == 2


@pytest.mark.asyncio
async def test_postgres_credentials_no_renewal_before_threshold(mock_config, mock_vault_client):
    """
    Testa que credenciais NÃO são renovadas antes do threshold
    """
    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    mock_vault_client.get_database_credentials.return_value = {
        "username": "user1", "password": "pass1", "ttl": 100
    }

    # Buscar credenciais iniciais
    await vault_integration.get_postgres_credentials()

    # Simular passagem de tempo (apenas 50% do TTL consumido)
    vault_integration._postgres_credentials_expiry = datetime.utcnow() + timedelta(seconds=50)

    # Chamar renovação
    await vault_integration._renew_postgres_credentials_if_needed()

    # Verificar que credenciais NÃO foram renovadas (apenas 1 chamada inicial)
    assert mock_vault_client.get_database_credentials.call_count == 1


@pytest.mark.asyncio
async def test_postgres_credentials_renewal_on_expiry(mock_config, mock_vault_client):
    """
    Testa renovação imediata quando credenciais expiradas
    """
    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    mock_vault_client.get_database_credentials.side_effect = [
        {"username": "user1", "password": "pass1", "ttl": 100},
        {"username": "user2", "password": "pass2", "ttl": 100}
    ]

    # Buscar credenciais iniciais
    await vault_integration.get_postgres_credentials()

    # Simular expiração (expiry no passado)
    vault_integration._postgres_credentials_expiry = datetime.utcnow() - timedelta(seconds=10)

    # Chamar renovação
    await vault_integration._renew_postgres_credentials_if_needed()

    # Verificar que credenciais foram renovadas imediatamente
    assert vault_integration._postgres_credentials["username"] == "user2"
    assert mock_vault_client.get_database_credentials.call_count == 2


@pytest.mark.asyncio
async def test_postgres_credentials_fallback_when_vault_disabled(mock_config):
    """
    Testa fallback para credenciais estáticas quando Vault desabilitado
    """
    mock_config.vault_enabled = False

    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = None  # Vault desabilitado
    vault_integration.config = mock_config

    # Buscar credenciais
    creds = await vault_integration.get_postgres_credentials()

    # Verificar que retornou credenciais estáticas da config
    assert creds["username"] == "static_user"
    assert creds["password"] == "static_password"
    assert creds["ttl"] == 0


@pytest.mark.asyncio
async def test_postgres_credentials_fail_open_on_error(mock_config, mock_vault_client):
    """
    Testa fail-open quando ocorre erro e vault_fail_open=True
    """
    mock_config.vault_fail_open = True

    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    # Simular erro no Vault
    mock_vault_client.get_database_credentials.side_effect = Exception("Vault connection error")

    # Buscar credenciais
    creds = await vault_integration.get_postgres_credentials()

    # Verificar que retornou credenciais estáticas (fail-open)
    assert creds["username"] == "static_user"
    assert creds["password"] == "static_password"


@pytest.mark.asyncio
async def test_postgres_credentials_fail_closed_on_error(mock_config, mock_vault_client):
    """
    Testa fail-closed quando ocorre erro e vault_fail_open=False
    """
    mock_config.vault_fail_open = False

    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    # Simular erro no Vault
    mock_vault_client.get_database_credentials.side_effect = Exception("Vault connection error")

    # Buscar credenciais deve levantar exceção
    with pytest.raises(Exception, match="Vault connection error"):
        await vault_integration.get_postgres_credentials()
