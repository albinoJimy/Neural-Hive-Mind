import os

import pytest
import pytest_asyncio
import structlog

from neural_hive_security import VaultClient, SPIFFEManager, VaultConfig, SPIFFEConfig
from src.clients.vault_integration import OrchestratorVaultClient
from src.config.settings import OrchestratorSettings

logger = structlog.get_logger(__name__)

REAL_E2E = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"


def require_real_env():
    """Skip tests unless explicitly enabled for real Vault/SPIRE environment."""
    if not REAL_E2E:
        pytest.skip("RUN_VAULT_SPIFFE_E2E not enabled")


def build_test_settings() -> OrchestratorSettings:
    """Cria OrchestratorSettings mínimos para testes E2E."""
    return OrchestratorSettings(
        kafka_bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
        kafka_consumer_group_id='orchestrator-dynamic-e2e',
        kafka_consensus_topic=os.getenv('KAFKA_CONSENSUS_TOPIC', 'plans.consensus'),
        postgres_host=os.getenv('POSTGRES_HOST', 'localhost'),
        postgres_user=os.getenv('POSTGRES_USER', 'temporal'),
        postgres_password=os.getenv('POSTGRES_PASSWORD', 'temporal'),
        mongodb_uri=os.getenv('MONGODB_URI', 'mongodb://localhost:27017'),
        redis_cluster_nodes=os.getenv('REDIS_CLUSTER_NODES', 'localhost:6379'),
        vault_enabled=True,
        vault_address=os.getenv('VAULT_ADDR', 'http://localhost:8200'),
        vault_kubernetes_role=os.getenv('VAULT_K8S_ROLE', 'orchestrator-dynamic'),
        vault_token_path=os.getenv('VAULT_TOKEN_PATH', '/var/run/secrets/kubernetes.io/serviceaccount/token'),
        spiffe_enabled=os.getenv('SPIFFE_ENABLED', 'false').lower() == 'true',
        spiffe_socket_path=os.getenv('SPIFFE_SOCKET_PATH', 'unix:///run/spire/sockets/agent.sock'),
        spiffe_trust_domain=os.getenv('SPIFFE_TRUST_DOMAIN', 'neural-hive.local'),
        spiffe_jwt_audience=os.getenv('SPIFFE_JWT_AUDIENCE', 'vault.neural-hive.local'),
    )


def build_vault_config() -> VaultConfig:
    """Configura Vault para testes."""
    return VaultConfig(
        address=os.getenv('VAULT_ADDR', 'http://localhost:8200'),
        namespace=os.getenv('VAULT_NAMESPACE', ''),
        auth_method=os.getenv('VAULT_AUTH_METHOD', 'kubernetes'),
        kubernetes_role=os.getenv('VAULT_K8S_ROLE', 'orchestrator-dynamic'),
        jwt_path=os.getenv('VAULT_TOKEN_PATH', '/var/run/secrets/kubernetes.io/serviceaccount/token'),
        mount_path_kv=os.getenv('VAULT_MOUNT_KV', 'secret'),
        mount_path_database=os.getenv('VAULT_MOUNT_DB', 'database'),
        fail_open=True,
    )


def build_spiffe_config() -> SPIFFEConfig:
    """Configura SPIFFE para testes."""
    return SPIFFEConfig(
        workload_api_socket=os.getenv('SPIFFE_SOCKET_PATH', 'unix:///run/spire/sockets/agent.sock'),
        trust_domain=os.getenv('SPIFFE_TRUST_DOMAIN', 'neural-hive.local'),
        jwt_audience=os.getenv('SPIFFE_JWT_AUDIENCE', 'vault.neural-hive.local'),
        jwt_ttl_seconds=int(os.getenv('SPIFFE_JWT_TTL_SECONDS', '3600')),
        enable_x509=os.getenv('SPIFFE_ENABLE_X509', 'false').lower() == 'true',
        environment=os.getenv('SPIFFE_ENVIRONMENT', 'development')
    )


@pytest_asyncio.fixture(scope="session")
async def vault_client():
    """Inicializa VaultClient real (requer ambiente configurado)."""
    require_real_env()
    config = build_vault_config()
    client = VaultClient(config)
    await client.initialize()
    yield client
    await client.close()


@pytest_asyncio.fixture(scope="session")
async def spiffe_manager():
    """Inicializa SPIFFEManager real (requer SPIRE agent)."""
    require_real_env()
    config = build_spiffe_config()
    manager = SPIFFEManager(config)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest_asyncio.fixture(scope="session")
async def orchestrator_vault_client():
    """Inicializa OrchestratorVaultClient para uso nos testes."""
    require_real_env()
    settings = build_test_settings()
    client = OrchestratorVaultClient(settings)
    await client.initialize()
    yield client
    await client.close()
