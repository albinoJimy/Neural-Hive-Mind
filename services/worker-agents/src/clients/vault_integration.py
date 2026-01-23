"""
Cliente de integração Vault para worker-agents service
"""

import asyncio
from typing import Dict, Optional, Callable, Any
from datetime import datetime, timedelta
import structlog
from prometheus_client import Counter

# Import security library components
try:
    from neural_hive_security import VaultClient, SPIFFEManager, VaultConfig, SPIFFEConfig
    from neural_hive_security import VaultConnectionError, VaultAuthenticationError
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False

from src.config.settings import WorkerAgentSettings


logger = structlog.get_logger(__name__)

# Métricas Prometheus
vault_credentials_fetched_total = Counter(
    "worker_vault_credentials_fetched_total",
    "Total de buscas de credenciais do Vault",
    ["credential_type", "status"]
)
vault_renewal_task_runs_total = Counter(
    "worker_vault_renewal_task_runs_total",
    "Execuções do task de renovação de credenciais",
    ["status"]
)


class WorkerVaultClient:
    """
    Cliente Vault para worker-agents

    Gerencia:
    - Credenciais de execução (AWS, Docker, etc.)
    - Credenciais Kafka com rotação automática
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

        # Cache de credenciais Kafka para gerenciar renovação
        self._kafka_credentials: Optional[Dict[str, Any]] = None
        self._kafka_credentials_expiry: Optional[datetime] = None
        self._renewal_task: Optional[asyncio.Task] = None

        # Callback para atualização de credenciais Kafka
        self._kafka_credential_update_callback: Optional[Callable] = None

        # Threshold para renovação (renovar quando 75% do TTL consumido)
        self._credential_renewal_threshold = getattr(
            config, 'vault_credential_renewal_threshold', 0.75
        )

    def set_kafka_credential_callback(self, callback: Callable):
        """
        Registra callback para atualização de credenciais Kafka.

        O callback será chamado quando novas credenciais forem obtidas do Vault,
        permitindo a recriação do producer Kafka.

        Args:
            callback: Async callable que recebe Dict com username, password
        """
        self._kafka_credential_update_callback = callback
        self.logger.info("kafka_credential_callback_registered")

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

                # Iniciar task de renovação de credenciais
                self._renewal_task = asyncio.create_task(self._renew_credentials_loop())
                self.logger.info("credential_renewal_task_started")

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
        """
        Busca credenciais Kafka do Vault com cache e TTL.

        Returns:
            Dict com username, password e ttl (se disponível)
        """
        if not self.vault_client or not self.config.vault_enabled:
            return {"username": None, "password": None, "ttl": 0}

        try:
            self.logger.debug("fetching_kafka_credentials")
            secret = await self.vault_client.read_secret("worker/kafka")

            if secret:
                ttl = secret.get("ttl", 0)

                # Armazenar credenciais e expiry para renovação
                self._kafka_credentials = {
                    "username": secret.get("username"),
                    "password": secret.get("password"),
                    "ttl": ttl
                }
                if ttl > 0:
                    self._kafka_credentials_expiry = datetime.utcnow() + timedelta(seconds=ttl)

                self.logger.info("kafka_credentials_fetched", ttl=ttl)
                vault_credentials_fetched_total.labels(credential_type="kafka", status="success").inc()

                return self._kafka_credentials

            return {"username": None, "password": None, "ttl": 0}

        except Exception as e:
            self.logger.error("kafka_credentials_fetch_failed", error=str(e))
            vault_credentials_fetched_total.labels(credential_type="kafka", status="error").inc()
            if self.config.vault_fail_open:
                return {"username": None, "password": None, "ttl": 0}
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

    async def _renew_credentials_loop(self):
        """
        Background task para renovação de credenciais Kafka.

        Monitora TTL e renova antes da expiração usando thresholds configurados.
        """
        self.logger.info("starting_credential_renewal_task")

        while True:
            try:
                if not self.vault_client or not self.config.vault_enabled:
                    await asyncio.sleep(300)  # 5 minutos
                    continue

                # Calcular próximo check baseado em credenciais existentes
                check_interval = self._calculate_next_check_interval()
                await asyncio.sleep(check_interval)

                self.logger.debug("checking_credential_renewal")

                # Verificar e renovar credenciais Kafka
                await self._renew_kafka_credentials_if_needed()

                self.logger.debug("credential_renewal_check_complete")
                vault_renewal_task_runs_total.labels(status="success").inc()

            except asyncio.CancelledError:
                self.logger.info("credential_renewal_task_cancelled")
                break
            except Exception as e:
                self.logger.error("credential_renewal_error", error=str(e))
                vault_renewal_task_runs_total.labels(status="error").inc()
                await asyncio.sleep(60)  # Backoff em caso de erro

    def _calculate_next_check_interval(self) -> int:
        """
        Calcula o próximo intervalo de verificação baseado nas credenciais existentes.

        Returns:
            Intervalo em segundos até a próxima verificação
        """
        if self._kafka_credentials_expiry:
            time_until_expiry = (self._kafka_credentials_expiry - datetime.utcnow()).total_seconds()
            if time_until_expiry > 0:
                # Verificar quando atingir o threshold
                check_at = time_until_expiry * (1 - self._credential_renewal_threshold)
                return max(int(check_at), 60)  # Mínimo 60s

        # Se não há credenciais para monitorar, verificar a cada 5 minutos
        return 300

    async def _renew_kafka_credentials_if_needed(self):
        """
        Verifica e renova credenciais Kafka se necessário.
        """
        if not self._kafka_credentials_expiry:
            return

        time_until_expiry = (self._kafka_credentials_expiry - datetime.utcnow()).total_seconds()
        if time_until_expiry <= 0:
            self.logger.warning("kafka_credentials_expired", expired_seconds_ago=abs(time_until_expiry))
            await self._fetch_and_update_kafka_credentials()
            return

        original_ttl = self._kafka_credentials.get("ttl", 0) if self._kafka_credentials else 0
        if original_ttl <= 0:
            return

        consumed_ratio = 1.0 - (time_until_expiry / original_ttl)

        if consumed_ratio >= (1.0 - self._credential_renewal_threshold):
            self.logger.info(
                "renewing_kafka_credentials",
                time_until_expiry=time_until_expiry,
                consumed_ratio=consumed_ratio
            )
            await self._fetch_and_update_kafka_credentials()

    async def _fetch_and_update_kafka_credentials(self):
        """
        Busca novas credenciais Kafka e notifica callback se registrado.
        """
        try:
            secret = await self.vault_client.read_secret("worker/kafka")

            if secret:
                ttl = secret.get("ttl", 0)
                new_creds = {
                    "username": secret.get("username"),
                    "password": secret.get("password"),
                    "ttl": ttl
                }

                self._kafka_credentials = new_creds
                if ttl > 0:
                    self._kafka_credentials_expiry = datetime.utcnow() + timedelta(seconds=ttl)

                self.logger.info(
                    "kafka_credentials_renewed",
                    ttl=ttl,
                    username=secret.get("username")
                )
                vault_credentials_fetched_total.labels(credential_type="kafka", status="renewed").inc()

                # Notificar callback para atualização do producer Kafka
                if self._kafka_credential_update_callback:
                    try:
                        await self._kafka_credential_update_callback(new_creds)
                        self.logger.info(
                            "kafka_credentials_callback_executed",
                            note="Kafka producer atualizado via callback"
                        )
                    except Exception as cb_error:
                        self.logger.error(
                            "kafka_credentials_callback_failed",
                            error=str(cb_error)
                        )
                else:
                    self.logger.warning(
                        "kafka_credentials_renewed_no_callback",
                        note="Nenhum callback registrado para atualização do Kafka producer"
                    )

        except Exception as e:
            self.logger.error("kafka_credentials_renewal_failed", error=str(e))
            vault_credentials_fetched_total.labels(credential_type="kafka", status="error").inc()
            raise

    async def close(self):
        """Cleanup"""
        self.logger.info("closing_worker_vault_integration")

        # Cancelar task de renovação
        if self._renewal_task:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except asyncio.CancelledError:
                pass

        if self.vault_client:
            await self.vault_client.close()

        if self.spiffe_manager and self._owns_spiffe:
            await self.spiffe_manager.close()
