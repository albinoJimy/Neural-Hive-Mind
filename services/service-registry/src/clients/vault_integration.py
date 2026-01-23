"""
Cliente de integração Vault para service-registry
"""

import asyncio
from typing import Dict, Optional
from datetime import datetime, timedelta
import structlog
from prometheus_client import Counter

# Import security library components
try:
    from neural_hive_security import VaultClient, VaultConfig
    from neural_hive_security import VaultConnectionError, VaultAuthenticationError
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    VaultClient = None
    VaultConfig = None
    VaultConnectionError = Exception
    VaultAuthenticationError = Exception


logger = structlog.get_logger(__name__)

vault_credentials_fetched_total = Counter(
    "service_registry_vault_credentials_fetched_total",
    "Total de buscas de credenciais do Vault",
    ["credential_type", "status"]
)


class ServiceRegistryVaultClient:
    """
    Cliente Vault para service-registry

    Gerencia:
    - Credenciais do etcd
    - Senha do Redis
    """

    def __init__(self, config):
        if not SECURITY_LIB_AVAILABLE:
            raise ImportError("neural-hive-security library not available")

        self.config = config
        self.logger = logger.bind(component="service_registry_vault_integration")

        # Create Vault config
        vault_config = VaultConfig(
            address=getattr(config, 'VAULT_ADDRESS', 'http://vault.vault.svc.cluster.local:8200'),
            namespace=getattr(config, 'VAULT_NAMESPACE', ''),
            auth_method=getattr(config, 'VAULT_AUTH_METHOD', 'kubernetes'),
            kubernetes_role=getattr(config, 'VAULT_KUBERNETES_ROLE', 'service-registry'),
            jwt_path=getattr(config, 'VAULT_TOKEN_PATH', '/vault/secrets/token'),
            mount_path_kv=getattr(config, 'VAULT_MOUNT_KV', 'secret'),
            timeout_seconds=getattr(config, 'VAULT_TIMEOUT_SECONDS', 5),
            max_retries=getattr(config, 'VAULT_MAX_RETRIES', 3),
            fail_open=getattr(config, 'VAULT_FAIL_OPEN', False),
        )

        self.vault_enabled = getattr(config, 'VAULT_ENABLED', False)
        self.vault_fail_open = getattr(config, 'VAULT_FAIL_OPEN', False)
        self.vault_client: Optional[VaultClient] = VaultClient(vault_config) if self.vault_enabled else None

    async def initialize(self):
        """Inicializa cliente Vault"""
        self.logger.info("initializing_service_registry_vault_integration")

        try:
            if self.vault_client and self.vault_enabled:
                self.logger.info("initializing_vault_client")
                await self.vault_client.initialize()
                self.logger.info("vault_client_initialized")

            self.logger.info("service_registry_vault_integration_initialized")

        except (VaultConnectionError, VaultAuthenticationError) as e:
            if not self.vault_fail_open:
                self.logger.error("vault_initialization_failed", error=str(e))
                raise
            else:
                self.logger.warning("vault_initialization_failed_failopen", error=str(e))

    async def get_etcd_credentials(self) -> Dict[str, str]:
        """
        Busca credenciais do etcd no Vault

        Returns:
            Dict com username, password
        """
        if not self.vault_client or not self.vault_enabled:
            return {
                "username": getattr(self.config, 'ETCD_USERNAME', ''),
                "password": getattr(self.config, 'ETCD_PASSWORD', '')
            }

        try:
            self.logger.debug("fetching_etcd_credentials")
            secret = await self.vault_client.read_secret("service-registry/etcd")

            if secret:
                self.logger.info("etcd_credentials_fetched")
                vault_credentials_fetched_total.labels(credential_type="etcd", status="success").inc()
                return {
                    "username": secret.get("username", ""),
                    "password": secret.get("password", "")
                }
            else:
                self.logger.warning("etcd_credentials_not_found_in_vault")
                return {
                    "username": getattr(self.config, 'ETCD_USERNAME', ''),
                    "password": getattr(self.config, 'ETCD_PASSWORD', '')
                }

        except Exception as e:
            self.logger.error("etcd_credentials_fetch_failed", error=str(e))
            vault_credentials_fetched_total.labels(credential_type="etcd", status="error").inc()
            if self.vault_fail_open:
                return {
                    "username": getattr(self.config, 'ETCD_USERNAME', ''),
                    "password": getattr(self.config, 'ETCD_PASSWORD', '')
                }
            raise

    async def get_redis_password(self) -> Optional[str]:
        """
        Busca senha do Redis no Vault

        Returns:
            Redis password
        """
        if not self.vault_client or not self.vault_enabled:
            return getattr(self.config, 'REDIS_PASSWORD', None)

        try:
            self.logger.debug("fetching_redis_password")
            secret = await self.vault_client.read_secret("service-registry/redis")

            if secret and "password" in secret:
                self.logger.info("redis_password_fetched")
                vault_credentials_fetched_total.labels(credential_type="redis", status="success").inc()
                return secret["password"]
            else:
                self.logger.warning("redis_password_not_found_in_vault")
                return getattr(self.config, 'REDIS_PASSWORD', None)

        except Exception as e:
            self.logger.error("redis_password_fetch_failed", error=str(e))
            vault_credentials_fetched_total.labels(credential_type="redis", status="error").inc()
            if self.vault_fail_open:
                return getattr(self.config, 'REDIS_PASSWORD', None)
            raise

    async def health_check(self) -> bool:
        """
        Verifica saúde da conexão com Vault

        Returns:
            True se Vault está healthy, False caso contrário
        """
        if not self.vault_client or not self.vault_enabled:
            return True  # Vault disabled is considered "healthy"

        try:
            return await self.vault_client.health_check()
        except Exception as e:
            self.logger.warning("vault_health_check_failed", error=str(e))
            return False

    async def close(self):
        """Cleanup"""
        self.logger.info("closing_service_registry_vault_integration")

        if self.vault_client:
            await self.vault_client.close()

        self.logger.info("service_registry_vault_integration_closed")
