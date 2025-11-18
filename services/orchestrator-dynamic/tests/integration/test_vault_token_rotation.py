"""
Testes de integração para rotação de tokens Vault e renovação de credenciais.

Testa cenários de:
- Renovação automática de token Vault
- Rotação de credenciais PostgreSQL dinâmicas
- Renovação de credenciais com TTL baixo
- Cancelamento de tarefas de renovação
- Fail-open/fail-closed behavior
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta


# Mock de configurações
@pytest.fixture
def mock_config():
    """Mock de configurações do orchestrator alinhado com OrchestratorSettings."""
    config = MagicMock()
    # Vault settings
    config.vault_enabled = True
    config.vault_address = "http://vault.vault.svc.cluster.local:8200"
    config.vault_namespace = "neural-hive"
    config.vault_auth_method = "kubernetes"
    config.vault_kubernetes_role = "orchestrator-dynamic"
    config.vault_token_path = "/vault/secrets/token"
    config.vault_mount_kv = "secret"
    config.vault_mount_database = "database"
    config.vault_timeout_seconds = 5
    config.vault_max_retries = 3
    config.vault_fail_open = True
    config.vault_token_renewal_threshold = 0.2  # Renovar em 80% do TTL (1-0.2)
    config.vault_db_credentials_renewal_threshold = 0.2

    # SPIFFE settings
    config.spiffe_enabled = True
    config.spiffe_socket_path = "unix:///run/spire/sockets/agent.sock"
    config.spiffe_trust_domain = "neural-hive.local"
    config.spiffe_jwt_audience = "vault.neural-hive.local"

    # Fallback credentials
    config.mongodb_uri = "mongodb://localhost:27017"
    config.postgres_user = "postgres"
    config.postgres_password = "postgres"
    config.redis_password = None
    config.kafka_sasl_username = None
    config.kafka_sasl_password = None

    return config


@pytest.fixture
def mock_vault_client():
    """Mock do VaultClient da biblioteca neural_hive_security."""
    mock_client = AsyncMock()
    mock_client.token = "s.test_token_12345"
    mock_client.token_expiry = datetime.utcnow() + timedelta(seconds=3600)
    mock_client.initialize = AsyncMock()
    mock_client.renew_token = AsyncMock(return_value=True)
    mock_client.get_database_credentials = AsyncMock(return_value={
        "username": "v-kubernet-temporal-orchestrator-abc123",
        "password": "A1b2C3d4E5f6G7h8",
        "ttl": 3600
    })
    mock_client.read_secret = AsyncMock(return_value={"uri": "mongodb://vault:27017"})
    mock_client.close = AsyncMock()
    return mock_client


@pytest.fixture
def mock_spiffe_manager():
    """Mock do SPIFFEManager da biblioteca neural_hive_security."""
    mock_manager = AsyncMock()
    mock_manager.initialize = AsyncMock()
    mock_manager.close = AsyncMock()
    return mock_manager


@pytest.mark.asyncio
async def test_vault_token_renewal_success(mock_config, mock_vault_client):
    """
    Testa renovação bem-sucedida do token Vault.

    Cenário:
    1. Cliente autentica com token inicial (TTL: 3600s)
    2. Tempo avança para 80% do TTL (2880s)
    3. Tarefa de renovação é acionada
    4. Token é renovado com sucesso
    5. Novo TTL é registrado
    """
    with patch('src.clients.vault_integration.VaultClient', return_value=mock_vault_client):
        with patch('src.clients.vault_integration.SPIFFEManager') as mock_spiffe:
            from src.clients.vault_integration import OrchestratorVaultClient

            # Criar cliente
            vault_client = OrchestratorVaultClient(mock_config)
            await vault_client.initialize()

            # Verificar que VaultClient foi inicializado
            assert mock_vault_client.initialize.called

            # Simular token próximo da expiração (20% do TTL restante = threshold)
            original_expiry = mock_vault_client.token_expiry
            mock_vault_client.token_expiry = datetime.utcnow() + timedelta(seconds=720)  # 20% de 3600

            # Chamar método de renovação diretamente
            await vault_client._renew_vault_token_if_needed()

            # Verificar que renew_token foi chamado
            assert mock_vault_client.renew_token.called

            # Cleanup
            await vault_client.close()


@pytest.mark.asyncio
async def test_postgres_credential_rotation(mock_config, mock_vault_client):
    """
    Testa rotação de credenciais PostgreSQL dinâmicas.

    Cenário:
    1. Cliente obtém credenciais iniciais (TTL: 3600s)
    2. Credenciais são armazenadas em cache
    3. Quando TTL atinge threshold (80% consumido), novas credenciais são obtidas
    """
    with patch('src.clients.vault_integration.VaultClient', return_value=mock_vault_client):
        with patch('src.clients.vault_integration.SPIFFEManager'):
            from src.clients.vault_integration import OrchestratorVaultClient

            vault_client = OrchestratorVaultClient(mock_config)
            await vault_client.initialize()

            # Primeira chamada: deve buscar do Vault e cachear
            creds1 = await vault_client.get_postgres_credentials()
            assert creds1['username'] == "v-kubernet-temporal-orchestrator-abc123"
            assert creds1['ttl'] == 3600
            assert vault_client._postgres_credentials is not None
            assert vault_client._postgres_credentials_expiry is not None

            # Configurar mock para retornar novas credenciais
            mock_vault_client.get_database_credentials.return_value = {
                "username": "v-kubernet-temporal-orchestrator-xyz789",
                "password": "Z9y8X7w6V5u4T3s2",
                "ttl": 3600
            }

            # Simular TTL baixo (20% restante = threshold)
            vault_client._postgres_credentials_expiry = datetime.utcnow() + timedelta(seconds=720)  # 20% de 3600

            # Chamar renovação
            await vault_client._renew_postgres_credentials_if_needed()

            # Verificar que novas credenciais foram obtidas
            assert vault_client._postgres_credentials['username'] == "v-kubernet-temporal-orchestrator-xyz789"

            await vault_client.close()


@pytest.mark.asyncio
async def test_credential_renewal_task_interval_calculation(mock_config, mock_vault_client):
    """
    Testa cálculo de intervalo de renovação baseado em TTLs.
    """
    with patch('src.clients.vault_integration.VaultClient', return_value=mock_vault_client):
        with patch('src.clients.vault_integration.SPIFFEManager'):
            from src.clients.vault_integration import OrchestratorVaultClient

            vault_client = OrchestratorVaultClient(mock_config)
            await vault_client.initialize()

            # Configurar TTLs
            mock_vault_client.token_expiry = datetime.utcnow() + timedelta(seconds=3600)
            vault_client._postgres_credentials_expiry = datetime.utcnow() + timedelta(seconds=1800)

            # Calcular intervalo
            interval = await vault_client._calculate_next_check_interval()

            # Deve retornar o menor intervalo (postgres com 1800s * 0.8 = 1440s)
            # Threshold é 0.2, então renova quando restam 20% = 1800 * 0.2 = 360s
            # Intervalo = 1800 - 360 = 1440s
            expected = int(1800 * (1 - mock_config.vault_db_credentials_renewal_threshold))
            assert interval <= expected + 1  # Permitir pequena variação de tempo

            await vault_client.close()


@pytest.mark.asyncio
async def test_renewal_task_cancellation_on_close(mock_config, mock_vault_client):
    """
    Testa que tarefa de renovação é cancelada corretamente ao fechar cliente.
    """
    with patch('src.clients.vault_integration.VaultClient', return_value=mock_vault_client):
        with patch('src.clients.vault_integration.SPIFFEManager'):
            from src.clients.vault_integration import OrchestratorVaultClient

            vault_client = OrchestratorVaultClient(mock_config)
            await vault_client.initialize()

            # Verificar que tarefa de renovação foi criada
            assert vault_client._renewal_task is not None
            assert not vault_client._renewal_task.done()

            # Fechar cliente
            await vault_client.close()

            # Aguardar cancelamento
            await asyncio.sleep(0.1)

            # Verificar que tarefa foi cancelada
            assert vault_client._renewal_task.cancelled() or vault_client._renewal_task.done()


@pytest.mark.asyncio
async def test_fail_open_on_vault_unavailable(mock_config):
    """
    Testa comportamento fail-open quando Vault está indisponível.

    Cenário:
    - Vault não responde
    - Cliente configurado com fail_open=True
    - Deve retornar credenciais estáticas de fallback
    """
    mock_config.vault_fail_open = True

    # Mock VaultClient que levanta exceção na inicialização
    mock_vault_client_failing = AsyncMock()
    mock_vault_client_failing.initialize = AsyncMock(side_effect=Exception("Connection refused"))

    with patch('src.clients.vault_integration.VaultClient', return_value=mock_vault_client_failing):
        with patch('src.clients.vault_integration.SPIFFEManager'):
            from src.clients.vault_integration import OrchestratorVaultClient

            vault_client = OrchestratorVaultClient(mock_config)

            # Initialize deve falhar gracefully em fail-open mode
            await vault_client.initialize()  # Não deve levantar exceção

            # Deve retornar credenciais de fallback (configuração)
            postgres_creds = await vault_client.get_postgres_credentials()
            assert postgres_creds['username'] == mock_config.postgres_user
            assert postgres_creds['password'] == mock_config.postgres_password
            assert postgres_creds['ttl'] == 0

            mongo_uri = await vault_client.get_mongodb_uri()
            assert mongo_uri == mock_config.mongodb_uri

            await vault_client.close()


@pytest.mark.asyncio
async def test_fail_closed_on_vault_unavailable(mock_config):
    """
    Testa comportamento fail-closed quando Vault está indisponível.

    Cenário:
    - Vault não responde
    - Cliente configurado com fail_open=False
    - Deve levantar exceção
    """
    mock_config.vault_fail_open = False

    # Mock VaultClient que levanta exceção na inicialização
    mock_vault_client_failing = AsyncMock()
    mock_vault_client_failing.initialize = AsyncMock(side_effect=Exception("Connection refused"))

    with patch('src.clients.vault_integration.VaultClient', return_value=mock_vault_client_failing):
        with patch('src.clients.vault_integration.SPIFFEManager'):
            from src.clients.vault_integration import OrchestratorVaultClient
            from neural_hive_security import VaultConnectionError, VaultAuthenticationError

            vault_client = OrchestratorVaultClient(mock_config)

            # Initialize deve levantar exceção em fail-closed mode
            # Note: Exception genérica será lançada se não for VaultConnectionError/VaultAuthenticationError
            with pytest.raises(Exception):
                await vault_client.initialize()

            await vault_client.close()


@pytest.mark.asyncio
async def test_postgres_credentials_expired_immediate_renewal(mock_config, mock_vault_client):
    """
    Testa renovação imediata quando credenciais PostgreSQL expiram.
    """
    with patch('src.clients.vault_integration.VaultClient', return_value=mock_vault_client):
        with patch('src.clients.vault_integration.SPIFFEManager'):
            from src.clients.vault_integration import OrchestratorVaultClient

            vault_client = OrchestratorVaultClient(mock_config)
            await vault_client.initialize()

            # Configurar credenciais expiradas
            vault_client._postgres_credentials = {
                "username": "old_user",
                "password": "old_pass",
                "ttl": 3600
            }
            vault_client._postgres_credentials_expiry = datetime.utcnow() - timedelta(seconds=10)  # Expirado

            # Configurar mock para retornar novas credenciais
            mock_vault_client.get_database_credentials.return_value = {
                "username": "new_user",
                "password": "new_pass",
                "ttl": 3600
            }

            # Chamar renovação
            await vault_client._renew_postgres_credentials_if_needed()

            # Verificar que novas credenciais foram obtidas
            assert vault_client._postgres_credentials['username'] == "new_user"
            assert mock_vault_client.get_database_credentials.called

            await vault_client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
