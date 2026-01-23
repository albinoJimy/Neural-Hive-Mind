"""
Testes de integração para rotação de credenciais Kafka via Vault
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
    config.kafka_sasl_username = "static_kafka_user"
    config.kafka_sasl_password = "static_kafka_pass"
    config.mongodb_uri = "mongodb://user:pass@localhost:27017"
    config.postgres_user = "pg_user"
    config.postgres_password = "pg_pass"
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
async def test_kafka_credentials_renewal_at_threshold(mock_config, mock_vault_client):
    """
    Testa renovação automática de credenciais Kafka quando threshold atingido
    """
    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    mock_vault_client.read_secret.side_effect = [
        {"username": "kafka_user1", "password": "kafka_pass1", "ttl": 100},
        {"username": "kafka_user2", "password": "kafka_pass2", "ttl": 100}
    ]

    # Buscar credenciais iniciais
    initial_creds = await vault_integration.get_kafka_credentials()
    assert initial_creds["username"] == "kafka_user1"
    assert initial_creds["ttl"] == 100

    # Simular passagem de tempo (81% do TTL consumido)
    vault_integration._kafka_credentials_expiry = datetime.utcnow() + timedelta(seconds=19)

    # Chamar renovação
    await vault_integration._renew_kafka_credentials_if_needed()

    # Verificar que credenciais foram renovadas
    assert vault_integration._kafka_credentials["username"] == "kafka_user2"
    assert mock_vault_client.read_secret.call_count == 2


@pytest.mark.asyncio
async def test_kafka_credentials_no_renewal_before_threshold(mock_config, mock_vault_client):
    """
    Testa que credenciais Kafka NÃO são renovadas antes do threshold
    """
    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    mock_vault_client.read_secret.return_value = {
        "username": "kafka_user1", "password": "kafka_pass1", "ttl": 100
    }

    # Buscar credenciais iniciais
    await vault_integration.get_kafka_credentials()

    # Simular passagem de tempo (apenas 50% do TTL consumido)
    vault_integration._kafka_credentials_expiry = datetime.utcnow() + timedelta(seconds=50)

    # Chamar renovação
    await vault_integration._renew_kafka_credentials_if_needed()

    # Verificar que credenciais NÃO foram renovadas (apenas 1 chamada inicial)
    assert mock_vault_client.read_secret.call_count == 1


@pytest.mark.asyncio
async def test_kafka_credentials_renewal_on_expiry(mock_config, mock_vault_client):
    """
    Testa renovação imediata de credenciais Kafka quando expiradas
    """
    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    mock_vault_client.read_secret.side_effect = [
        {"username": "kafka_user1", "password": "kafka_pass1", "ttl": 100},
        {"username": "kafka_user2", "password": "kafka_pass2", "ttl": 100}
    ]

    # Buscar credenciais iniciais
    await vault_integration.get_kafka_credentials()

    # Simular expiração (expiry no passado)
    vault_integration._kafka_credentials_expiry = datetime.utcnow() - timedelta(seconds=10)

    # Chamar renovação
    await vault_integration._renew_kafka_credentials_if_needed()

    # Verificar que credenciais foram renovadas imediatamente
    assert vault_integration._kafka_credentials["username"] == "kafka_user2"
    assert mock_vault_client.read_secret.call_count == 2


@pytest.mark.asyncio
async def test_kafka_credentials_fallback_when_vault_disabled(mock_config, mock_vault_client):
    """
    Testa fallback para credenciais estáticas quando Vault desabilitado
    """
    mock_config.vault_enabled = False

    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = None  # Vault desabilitado
    vault_integration.config = mock_config

    # Buscar credenciais
    creds = await vault_integration.get_kafka_credentials()

    # Verificar que retornou credenciais estáticas da config
    assert creds["username"] == "static_kafka_user"
    assert creds["password"] == "static_kafka_pass"
    assert creds["ttl"] == 0


@pytest.mark.asyncio
async def test_kafka_credentials_fail_open_on_error(mock_config, mock_vault_client):
    """
    Testa fail-open quando ocorre erro e vault_fail_open=True
    """
    mock_config.vault_fail_open = True

    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    # Simular erro no Vault
    mock_vault_client.read_secret.side_effect = Exception("Vault connection error")

    # Buscar credenciais
    creds = await vault_integration.get_kafka_credentials()

    # Verificar que retornou credenciais estáticas (fail-open)
    assert creds["username"] == "static_kafka_user"
    assert creds["password"] == "static_kafka_pass"


@pytest.mark.asyncio
async def test_kafka_credentials_fail_closed_on_error(mock_config, mock_vault_client):
    """
    Testa fail-closed quando ocorre erro e vault_fail_open=False
    """
    mock_config.vault_fail_open = False

    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    # Simular erro no Vault
    mock_vault_client.read_secret.side_effect = Exception("Vault connection error")

    # Buscar credenciais deve levantar exceção
    with pytest.raises(Exception, match="Vault connection error"):
        await vault_integration.get_kafka_credentials()


@pytest.mark.asyncio
async def test_kafka_credentials_not_found_in_vault(mock_config, mock_vault_client):
    """
    Testa comportamento quando credenciais Kafka não encontradas no Vault
    """
    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    # Simular secret não encontrado
    mock_vault_client.read_secret.return_value = None

    # Buscar credenciais
    creds = await vault_integration.get_kafka_credentials()

    # Verificar que retornou credenciais estáticas como fallback
    assert creds["username"] == "static_kafka_user"
    assert creds["password"] == "static_kafka_pass"
    assert creds["ttl"] == 0


@pytest.mark.asyncio
async def test_kafka_credentials_with_zero_ttl_no_expiry_tracking(mock_config, mock_vault_client):
    """
    Testa que credenciais com TTL=0 não têm tracking de expiração
    """
    OrchestratorVaultClient = get_vault_integration_class()

    vault_integration = OrchestratorVaultClient(mock_config)
    vault_integration.vault_client = mock_vault_client
    vault_integration.config = mock_config

    # Credenciais sem TTL
    mock_vault_client.read_secret.return_value = {
        "username": "kafka_user1", "password": "kafka_pass1", "ttl": 0
    }

    # Buscar credenciais iniciais
    creds = await vault_integration.get_kafka_credentials()
    assert creds["username"] == "kafka_user1"
    assert creds["ttl"] == 0

    # Verificar que expiry não foi setado
    assert vault_integration._kafka_credentials_expiry is None

    # Chamar renovação - não deve tentar renovar porque TTL=0
    await vault_integration._renew_kafka_credentials_if_needed()

    # Verificar que não houve chamada adicional
    assert mock_vault_client.read_secret.call_count == 1
