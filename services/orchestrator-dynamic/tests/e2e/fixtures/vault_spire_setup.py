"""
Fixtures para testes E2E de Vault e SPIFFE.

Estes fixtures suportam dois modos:
1. Mock mode (padrão): Usa MagicMock para testes unitários
2. Real E2E mode (RUN_VAULT_SPIFFE_E2E=true): Conecta a Vault/SPIRE reais via docker-compose

Para rodar testes E2E:
1. docker-compose -f tests/e2e/docker-compose.e2e up -d
2. RUN_VAULT_SPIFFE_E2E=true pytest tests/e2e/test_vault_spiffe_e2e.py
"""

import os
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Generator, Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx

# Import condicional para evitar erros quando neural_hive_security não disponível
try:
    from neural_hive_security import (
        VaultClient,
        VaultConfig,
        SPIFFEManager,
        SPIFFEConfig,
        VaultConnectionError,
        VaultAuthenticationError,
        SPIFFEConnectionError,
        JWTSVID,
        X509SVID,
    )

    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    VaultClient = None  # type: ignore
    VaultConfig = None  # type: ignore
    SPIFFEManager = None  # type: ignore
    SPIFFEConfig = None  # type: ignore
    VaultConnectionError = Exception
    VaultAuthenticationError = Exception
    SPIFFEConnectionError = Exception
    JWTSVID = None
    X509SVID = None

from src.config.settings import OrchestratorSettings
from src.clients.vault_integration import OrchestratorVaultClient

# Verificar se devemos rodar testes E2E reais
REAL_E2E = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"

# Configurações E2E reais
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://localhost:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "dev-root-token")
SPIFFE_SOCKET = os.getenv("SPIFFE_WORKLOAD_API_SOCKET", "unix:///run/spire/sockets/agent.sock")
SPIFFE_TRUST_DOMAIN = os.getenv("SPIFFE_TRUST_DOMAIN", "neural-hive.local")


def require_real_env():
    """Levanta exceção se não estiver em ambiente E2E real."""
    if not REAL_E2E:
        pytest.skip("RUN_VAULT_SPIFFE_E2E not enabled - set to 'true' to run real E2E tests")


def wait_for_service(url: str, timeout: int = 30) -> bool:
    """Aguarda serviço estar disponível."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = httpx.get(url, timeout=2)
            if response.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


async def wait_for_vault(timeout: int = 30) -> bool:
    """Aguarda Vault estar pronto."""
    url = f"{VAULT_ADDR}/v1/sys/health"
    start = time.time()
    while time.time() - start < timeout:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=2)
                if response.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


@pytest.fixture
async def settings_e2e() -> OrchestratorSettings:
    """Configurações para testes E2E."""
    settings = OrchestratorSettings()

    # Override com valores E2E
    settings.vault_address = VAULT_ADDR
    settings.vault_role = os.getenv("VAULT_ROLE", "orchestrator")
    settings.vault_auth_path = os.getenv("VAULT_AUTH_PATH", "kubernetes")
    settings.vault_auth_method = os.getenv("VAULT_AUTH_METHOD", "kubernetes")
    settings.vault_enabled = True
    settings.vault_fail_open = os.getenv("VAULT_FAIL_OPEN", "false").lower() == "true"
    settings.vault_token_ttl_seconds = int(os.getenv("VAULT_TOKEN_TTL", "3600"))
    settings.vault_token_renewal_threshold = float(os.getenv("VAULT_RENEW_THRESHOLD", "0.8"))
    settings.vault_mount_kv = os.getenv("VAULT_MOUNT_KV", "secret")
    settings.vault_mount_database = os.getenv("VAULT_MOUNT_DATABASE", "database")
    settings.vault_timeout_seconds = int(os.getenv("VAULT_TIMEOUT", "10"))

    # SPIFFE config
    settings.spiffe_enabled = os.getenv("SPIFFE_ENABLED", "true").lower() == "true"
    settings.spiffe_socket_path = SPIFFE_SOCKET
    settings.spiffe_trust_domain = SPIFFE_TRUST_DOMAIN
    settings.spiffe_jwt_audience = os.getenv("SPIFFE_JWT_AUDIENCE", "vault.neural-hive.local")
    settings.spiffe_jwt_ttl_seconds = int(os.getenv("SPIFFE_JWT_TTL", "3600"))
    settings.spiffe_fallback_allowed = os.getenv("SPIFFE_FALLLOW", "true").lower() == "true"

    # Database config
    settings.postgres_host = os.getenv("POSTGRES_HOST", "localhost")
    settings.postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
    settings.postgres_user = os.getenv("POSTGRES_USER", "postgres")
    settings.postgres_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    settings.postgres_db = os.getenv("POSTGRES_DB", "test_db")

    # Fallback credentials
    settings.mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/test")
    settings.redis_password = os.getenv("REDIS_PASSWORD", "test_redis_pass")
    settings.kafka_sasl_username = os.getenv("KAFKA_USERNAME", "test_kafka_user")
    settings.kafka_sasl_password = os.getenv("KAFKA_PASSWORD", "test_kafka_pass")

    return settings


@pytest.fixture
async def vault_client_real(settings_e2e: OrchestratorSettings) -> AsyncMock:
    """
    Cliente Vault real para testes E2E.

    Requer RUN_VAULT_SPIFFE_E2E=true e Vault rodando via docker-compose.
    """
    require_real_env()

    if not SECURITY_LIB_AVAILABLE:
        pytest.skip("neural-hive-security library not available")

    # Aguardar Vault estar pronto
    require_real_env()
    assert await wait_for_vault(60), "Vault não ficou pronto em 60 segundos"

    # Criar config
    config = VaultConfig(
        address=settings_e2e.vault_address,
        auth_method=settings_e2e.vault_auth_method,
        kubernetes_role=settings_e2e.vault_role,
        mount_path_kv=settings_e2e.vault_mount_kv,
        mount_path_database=settings_e2e.vault_mount_database,
        mount_path_pki="pki",
        timeout_seconds=10,
        fail_open=settings_e2e.vault_fail_open,
    )

    # Criar cliente
    client = VaultClient(config)

    # Setup inicial com token root (para testes)
    client.token = VAULT_TOKEN
    client.client = httpx.AsyncClient(
        base_url=VAULT_ADDR, timeout=10.0, headers={"X-Vault-Token": VAULT_TOKEN}
    )
    client.token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    yield client

    # Cleanup
    try:
        if client._renewal_task:
            client._renewal_task.cancel()
        if client.client:
            await client.client.aclose()
    except Exception:
        pass


@pytest.fixture
def vault_client_mock() -> AsyncMock:
    """Mock Vault client para testes unitários."""
    client = AsyncMock()
    client.token = "mock_token"
    client.token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    client.read_secret = AsyncMock(
        return_value={
            "uri": "mongodb://mock:mock@localhost:27017/test",
            "password": "mock_password",
        }
    )
    client.write_secret = AsyncMock()
    client.get_database_credentials = AsyncMock(
        return_value={
            "username": "v_test_user_abc123",
            "password": "v_test_pass_xyz789",
            "ttl": 3600,
        }
    )
    client.renew_token = AsyncMock(return_value=True)
    client.issue_certificate = AsyncMock(
        return_value={
            "certificate": "-----BEGIN CERTIFICATE-----\nmock_cert\n-----END CERTIFICATE-----",
            "private_key": "-----BEGIN PRIVATE KEY-----\nmock_key\n-----END PRIVATE KEY-----",
            "ca_chain": "-----BEGIN CERTIFICATE-----\nmock_ca\n-----END CERTIFICATE-----",
        }
    )
    return client


@pytest.fixture
async def vault_client(
    settings_e2e: OrchestratorSettings, vault_client_real: AsyncMock, vault_client_mock: AsyncMock
) -> Any:
    """
    Cliente Vault (real ou mock dependendo do modo).
    """
    if REAL_E2E:
        yield vault_client_real
    else:
        yield vault_client_mock


@pytest.fixture
async def spiffe_manager_real(settings_e2e: OrchestratorSettings) -> AsyncMock:
    """
    SPIFFE Manager real para testes E2E.

    Requer RUN_VAULT_SPIFFE_E2E=true e SPIRE rodando via docker-compose.
    """
    require_real_env()

    if not SECURITY_LIB_AVAILABLE:
        pytest.skip("neural-hive-security library not available")

    # Criar config
    config = SPIFFEConfig(
        workload_api_socket=settings_e2e.spiffe_socket_path,
        trust_domain=settings_e2e.spiffe_trust_domain,
        jwt_audience=settings_e2e.spiffe_jwt_audience,
        jwt_ttl_seconds=settings_e2e.spiffe_jwt_ttl_seconds,
        environment="development",  # Permite fallback em testes
    )

    # Criar manager
    manager = SPIFFEManager(config)

    yield manager

    # Cleanup
    try:
        await manager.close()
    except Exception:
        pass


@pytest.fixture
def spiffe_manager_mock() -> AsyncMock:
    """Mock SPIFFE manager para testes unitários."""
    manager = MagicMock()

    # Mock JWTSVID
    mock_jwt_svid = MagicMock(spec=JWTSVID) if JWTSVID else MagicMock()
    mock_jwt_svid.token = "mock_jwt_token_ey...mock"
    mock_jwt_svid.spiffe_id = "spiffe://neural-hive.local/test/orchestrator"
    mock_jwt_svid.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_jwt_svid.is_placeholder = False

    # Mock X509SVID
    mock_x509_svid = MagicMock(spec=X509SVID) if X509SVID else MagicMock()
    mock_x509_svid.certificate = "-----BEGIN CERTIFICATE-----\nmock_x509\n-----END CERTIFICATE-----"
    mock_x509_svid.private_key = "-----BEGIN PRIVATE KEY-----\nmock_key\n-----END PRIVATE KEY-----"
    mock_x509_svid.spiffe_id = "spiffe://neural-hive.local/test/orchestrator"
    mock_x509_svid.ca_bundle = "-----BEGIN CERTIFICATE-----\nmock_ca\n-----END CERTIFICATE-----"
    mock_x509_svid.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    manager.initialize = AsyncMock()
    manager.close = AsyncMock()
    manager.fetch_jwt_svid = AsyncMock(return_value=mock_jwt_svid)
    manager.fetch_x509_svid = AsyncMock(return_value=mock_x509_svid)
    manager.get_trust_bundle = AsyncMock(
        return_value="-----BEGIN CERTIFICATE-----\nmock_ca\n-----END CERTIFICATE-----"
    )
    manager.get_trust_bundle_keys = AsyncMock(return_value={"kid1": "mock_key"})

    return manager


@pytest.fixture
async def spiffe_manager(
    settings_e2e: OrchestratorSettings,
    spiffe_manager_real: AsyncMock,
    spiffe_manager_mock: MagicMock,
) -> Any:
    """
    SPIFFE Manager (real ou mock dependendo do modo).
    """
    if REAL_E2E:
        yield spiffe_manager_real
    else:
        yield spiffe_manager_mock


@pytest.fixture
async def orchestrator_vault_client_real(
    settings_e2e: OrchestratorSettings,
) -> OrchestratorVaultClient:
    """
    Cliente Vault do Orchestrator real para testes E2E.
    """
    require_real_env()

    if not SECURITY_LIB_AVAILABLE:
        pytest.skip("neural-hive-security library not available")

    client = OrchestratorVaultClient(settings_e2e)

    try:
        await client.initialize()
    except Exception as e:
        # Em fail-open, continua mesmo com erro
        if not settings_e2e.vault_fail_open:
            raise

    yield client

    # Cleanup
    try:
        await client.close()
    except Exception:
        pass


@pytest.fixture
def orchestrator_vault_client_mock() -> OrchestratorVaultClient:
    """Mock OrchestratorVaultClient para testes unitários."""
    settings = OrchestratorSettings()
    settings.vault_enabled = False  # Desabilita Vault real
    settings.vault_fail_open = True
    settings.postgres_user = "test_user"
    settings.postgres_password = "test_pass"
    settings.mongodb_uri = "mongodb://localhost:27017/test"
    settings.redis_password = "test_redis_pass"
    settings.kafka_sasl_username = "test_kafka_user"
    settings.kafka_sasl_password = "test_kafka_pass"

    client = OrchestratorVaultClient(settings)
    client.vault_client = None  # Simula Vault indisponível

    return client


@pytest.fixture
async def orchestrator_vault_client(
    settings_e2e: OrchestratorSettings,
    orchestrator_vault_client_real: OrchestratorVaultClient,
    orchestrator_vault_client_mock: OrchestratorVaultClient,
) -> OrchestratorVaultClient:
    """
    Cliente Vault do Orchestrator (real ou mock dependendo do modo).
    """
    if REAL_E2E:
        yield orchestrator_vault_client_real
    else:
        yield orchestrator_vault_client_mock


@pytest.fixture
def build_test_settings() -> OrchestratorSettings:
    """
    Constrói configurações de teste para Orchestrator.

    Usa variáveis de ambiente quando disponíveis, senão usa defaults.
    """
    settings = OrchestratorSettings()

    # Override com variáveis de ambiente ou defaults de teste
    settings.vault_address = os.getenv("VAULT_ADDR", "http://localhost:8200")
    settings.vault_role = os.getenv("VAULT_ROLE", "orchestrator")
    settings.vault_auth_path = os.getenv("VAULT_AUTH_PATH", "kubernetes")
    settings.vault_enabled = os.getenv("VAULT_ENABLED", "false").lower() == "true"
    settings.vault_fail_open = os.getenv("VAULT_FAIL_OPEN", "true").lower() == "true"
    settings.vault_token_ttl_seconds = int(os.getenv("VAULT_TOKEN_TTL", "3600"))

    # Credenciais de fallback
    settings.postgres_user = os.getenv("POSTGRES_USER", "test_user")
    settings.postgres_password = os.getenv("POSTGRES_PASSWORD", "test_pass")
    settings.mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/test")
    settings.redis_password = os.getenv("REDIS_PASSWORD", "test_redis_pass")

    # Kafka credentials
    settings.kafka_sasl_username = os.getenv("KAFKA_USERNAME", "test_kafka_user")
    settings.kafka_sasl_password = os.getenv("KAFKA_PASSWORD", "test_kafka_pass")

    # SPIFFE
    settings.spiffe_enabled = os.getenv("SPIFFE_ENABLED", "false").lower() == "true"
    settings.spiffe_socket_path = os.getenv("SPIFFE_SOCKET", "unix:///run/spire/sockets/agent.sock")
    settings.spiffe_trust_domain = os.getenv("SPIFFE_TRUST_DOMAIN", "neural-hive.local")

    return settings


@pytest.fixture
def teardown_secrets(vault_client) -> Generator[None, None, None]:
    """
    Fixture para limpar segredos criados durante testes.

    Uso:
        vault_client.write_secret("test/path", {"key": "value"})
        yield
        # após teste, remove segredo
    """
    created_paths = []

    def track_path(path: str):
        created_paths.append(path)

    def cleanup():
        for path in created_paths:
            try:
                # Tentar deletar (se KV v2, precisa de metadata)
                if REAL_E2E and vault_client.client:
                    try:
                        asyncio.run(vault_client.client.delete(f"/v1/secret/metadata/{path}"))
                    except Exception:
                        pass
            except Exception:
                pass

    yield track_path

    cleanup()


@pytest.fixture
async def expired_token_fixture() -> tuple[str, datetime]:
    """
    Fixture que fornece um token expirado e data de expiração.
    """
    expired_token = "s.expired_token_12345"
    expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
    return expired_token, expired_time


@pytest.fixture
def vault_unavailable_config() -> VaultConfig:
    """
    Config Vault com endereço indisponível para testar fail modes.
    """
    return VaultConfig(
        address="http://127.0.0.1:9999",  # Porta inválida
        timeout_seconds=2,
        fail_open=False,
    )


@pytest.fixture
def vault_unavailable_config_fail_open() -> VaultConfig:
    """
    Config Vault com fail_open para testar fallback.
    """
    return VaultConfig(
        address="http://127.0.0.1:9999",  # Porta inválida
        timeout_seconds=2,
        fail_open=True,
    )
