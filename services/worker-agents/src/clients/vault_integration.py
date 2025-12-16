"""
Cliente de integração Vault para worker-agents service
"""

import asyncio
from typing import Dict, Optional
import structlog

# Import security library components
try:
    from neural_hive_security import VaultClient, SPIFFEManager, VaultConfig, SPIFFEConfig
    from neural_hive_security import VaultConnectionError, VaultAuthenticationError
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False

from src.config.settings import WorkerAgentSettings


logger = structlog.get_logger(__name__)


class WorkerVaultClient:
    """
    Cliente Vault para worker-agents

    Gerencia:
    - Credenciais de execução (AWS, Docker, etc.)
    - Credenciais Kafka
    - Armazenamento de resultados sensíveis
    """

    def __init__(self, config: WorkerAgentSettings, spiffe_manager: Optional["SPIFFEManager"] = None):
        if not SECURITY_LIB_AVAILABLE:
            raise ImportError("neural-hive-security library not available")

        self.config = config
        self.logger = logger.bind(component="worker_vault_integration")

        # Create Vault config
        vault_config = VaultConfig(
            address=config.vault_address,
            kubernetes_role=config.vault_kubernetes_role,
            jwt_path=config.vault_token_path,
            mount_path_kv=config.vault_mount_kv,
            fail_open=config.vault_fail_open,
        )

        # Create SPIFFE config
        spiffe_config = SPIFFEConfig(
            workload_api_socket=config.spiffe_socket_path,
            trust_domain=config.spiffe_trust_domain,
            jwt_audience=config.spiffe_jwt_audience,
            jwt_ttl_seconds=config.spiffe_jwt_ttl_seconds,
        )

        self.vault_client: Optional[VaultClient] = VaultClient(vault_config) if config.vault_enabled else None
        self._owns_spiffe = spiffe_manager is None
        if spiffe_manager is not None:
            self.spiffe_manager = spiffe_manager
        else:
            self.spiffe_manager: Optional[SPIFFEManager] = SPIFFEManager(spiffe_config) if config.spiffe_enabled else None

    async def initialize(self):
        """Inicializa clientes Vault e SPIFFE"""
        self.logger.info("initializing_worker_vault_integration")

        try:
            # Initialize SPIFFE manager
            if self.spiffe_manager and self.config.spiffe_enabled and self._owns_spiffe:
                await self.spiffe_manager.initialize()

            # Initialize Vault client
            if self.vault_client and self.config.vault_enabled:
                await self.vault_client.initialize()

            self.logger.info("worker_vault_integration_initialized")

        except Exception as e:
            if not self.config.vault_fail_open:
                raise
            else:
                self.logger.warning("vault_initialization_failed_failopen", error=str(e))

    async def get_execution_credentials(self, task_type: str) -> Dict[str, str]:
        """
        Busca credenciais de execução específicas por tipo de task

        Args:
            task_type: Tipo de task (BUILD, DEPLOY, etc.)

        Returns:
            Dict com credenciais
        """
        if not self.vault_client or not self.config.vault_enabled:
            return {}

        try:
            path = f"worker/execution/{task_type.lower()}"
            secret = await self.vault_client.read_secret(path)
            return secret if secret else {}
        except Exception as e:
            self.logger.error("execution_credentials_fetch_failed", task_type=task_type, error=str(e))
            if self.config.vault_fail_open:
                return {}
            raise

    async def get_kafka_credentials(self) -> Dict[str, Optional[str]]:
        """Busca credenciais Kafka do Vault"""
        if not self.vault_client or not self.config.vault_enabled:
            return {"username": None, "password": None}

        try:
            secret = await self.vault_client.read_secret("worker/kafka")
            if secret:
                return {
                    "username": secret.get("username"),
                    "password": secret.get("password")
                }
            return {"username": None, "password": None}
        except Exception as e:
            self.logger.error("kafka_credentials_fetch_failed", error=str(e))
            if self.config.vault_fail_open:
                return {"username": None, "password": None}
            raise

    async def get_service_registry_token(self) -> Optional[str]:
        """Busca JWT token para autenticação no Service Registry"""
        if not self.spiffe_manager or not self.config.spiffe_enabled:
            return None

        try:
            jwt_svid = await self.spiffe_manager.fetch_jwt_svid("service-registry.neural-hive.local")
            return jwt_svid.token
        except Exception as e:
            self.logger.error("service_registry_token_fetch_failed", error=str(e))
            return None

    async def store_execution_result(self, ticket_id: str, result: Dict) -> bool:
        """
        Armazena resultado sensível de execução no Vault

        Args:
            ticket_id: ID do ticket de execução
            result: Resultado contendo dados sensíveis

        Returns:
            True se armazenado com sucesso
        """
        if not self.vault_client or not self.config.vault_enabled:
            return False

        try:
            path = f"worker/results/{ticket_id}"
            await self.vault_client.write_secret(path, result)
            self.logger.info("execution_result_stored", ticket_id=ticket_id)
            return True
        except Exception as e:
            self.logger.error("execution_result_store_failed", ticket_id=ticket_id, error=str(e))
            return False

    async def close(self):
        """Cleanup"""
        self.logger.info("closing_worker_vault_integration")

        if self.vault_client:
            await self.vault_client.close()

        if self.spiffe_manager and self._owns_spiffe:
            await self.spiffe_manager.close()
