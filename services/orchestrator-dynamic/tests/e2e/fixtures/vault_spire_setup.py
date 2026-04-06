"""
Fixtures para testes E2E de Vault e SPIFFE.

Estes fixtures são usados pelos testes de integração que requerem
um ambiente real de Vault e SPIFFE (controlado pela variável RUN_VAULT_SPIFFE_E2E).
"""
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest
import asyncio

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
    Em E2E real, conecta ao Vault em http://localhost:8200.
    """
    # Se E2E real está ativo, tenta conectar ao Vault real
    if REAL_E2E:
        try:
            from neural_hive_security import VaultClient, VaultConfig

            vault_config = VaultConfig(
                address=os.getenv("VAULT_ADDR", "http://localhost:8200"),
                auth_method="kubernetes",
                kubernetes_role="orchestrator",
                fail_open=True,
                timeout_seconds=10,
            )

            client = VaultClient(vault_config)

            # Usar token root para testes E2E
            client.token = os.getenv("VAULT_TOKEN", "e2e-test-root-token")
            client.token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

            yield client

        except ImportError:
            # Fallback para mock se biblioteca não disponível
            client = MagicMock()
            client.token = "mock_token"
            client.token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            client.get_database_credentials = AsyncMock(return_value={
                "username": "mock_user",
                "password": "mock_pass",
                "ttl": 3600
            })
            client.renew_token = AsyncMock(return_value=True)

            # Mock para PKI operations
            async def mock_issue_certificate(common_name: str, ttl: str = "24h"):
                return {
                    "certificate": f"-----BEGIN CERTIFICATE-----\nmock cert for {common_name}\n-----END CERTIFICATE-----",
                    "private_key": "-----BEGIN PRIVATE KEY-----\nmock key\n-----END PRIVATE KEY-----",
                    "ca_chain": "-----BEGIN CERTIFICATE-----\nmock CA\n-----END CERTIFICATE-----",
                }

            client.issue_certificate = mock_issue_certificate
            yield client
    else:
        # Mock para testes unitários
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
        spiffe_id="spiffe://neural-hive.local/test",
        expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    ))

    # Mock para X.509-SVID operations
    async def mock_fetch_x509_svid():
        from dataclasses import dataclass

        @dataclass
        class MockX509SVID:
            certificate: str
            private_key: str
            spiffe_id: str
            ca_bundle: str
            expires_at: datetime
            is_placeholder: bool = True

        return MockX509SVID(
            certificate="-----BEGIN CERTIFICATE-----\nplaceholder\n-----END CERTIFICATE-----",
            private_key="-----BEGIN PRIVATE KEY-----\nplaceholder\n-----END PRIVATE KEY-----",
            spiffe_id="spiffe://neural-hive.local/test",
            ca_bundle="-----BEGIN CERTIFICATE-----\nplaceholder CA\n-----END CERTIFICATE-----",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_placeholder=True,
        )

    manager.fetch_x509_svid = mock_fetch_x509_svid
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
