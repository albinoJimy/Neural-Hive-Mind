"""
Cliente de integração Vault para orchestrator-dynamic service
"""

import asyncio
from typing import Dict, Optional
from datetime import datetime, timedelta
import structlog
from prometheus_client import Counter

# Import security library components
try:
    from neural_hive_security import VaultClient, SPIFFEManager, VaultConfig, SPIFFEConfig
    from neural_hive_security import VaultConnectionError, VaultAuthenticationError, SPIFFEConnectionError
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False

from src.config.settings import OrchestratorSettings


logger = structlog.get_logger(__name__)

vault_credentials_fetched_total = Counter(
    "orchestrator_vault_credentials_fetched_total",
    "Total de buscas de credenciais do Vault",
    ["credential_type", "status"]
)
vault_renewal_task_runs_total = Counter(
    "orchestrator_vault_renewal_task_runs_total",
    "Execuções do task de renovação de credenciais",
    ["status"]
)


class OrchestratorVaultClient:
    """
    Cliente Vault para orchestrator-dynamic

    Gerencia:
    - Credenciais dinâmicas de PostgreSQL
    - Secrets do MongoDB
    - Credenciais do Redis
    - Credenciais do Kafka
    """

    def __init__(self, config: OrchestratorSettings):
        if not SECURITY_LIB_AVAILABLE:
            raise ImportError("neural-hive-security library not available")

        self.config = config
        self.logger = logger.bind(component="vault_integration")

        # Create Vault config from orchestrator settings
        # fail_open segue exatamente o vault_fail_open do OrchestratorSettings; os métodos de fetch fazem o fallback
        # final para credenciais estáticas quando necessário.
        vault_config = VaultConfig(
            address=config.vault_address,
            namespace=config.vault_namespace,
            auth_method=config.vault_auth_method,
            kubernetes_role=config.vault_kubernetes_role,
            jwt_path=config.vault_token_path,
            mount_path_kv=config.vault_mount_kv,
            mount_path_database=config.vault_mount_database,
            timeout_seconds=config.vault_timeout_seconds,
            max_retries=config.vault_max_retries,
            fail_open=config.vault_fail_open,
        )

        # Create SPIFFE config from orchestrator settings
        spiffe_config = SPIFFEConfig(
            workload_api_socket=config.spiffe_socket_path,
            trust_domain=config.spiffe_trust_domain,
            jwt_audience=config.spiffe_jwt_audience,
            jwt_ttl_seconds=config.spiffe_jwt_ttl_seconds,
        )

        self.vault_client: Optional[VaultClient] = VaultClient(vault_config) if config.vault_enabled else None
        self.spiffe_manager: Optional[SPIFFEManager] = SPIFFEManager(spiffe_config) if config.spiffe_enabled else None
        self._renewal_task: Optional[asyncio.Task] = None

        # Cache de credenciais PostgreSQL para gerenciar renovação
        self._postgres_credentials: Optional[Dict[str, any]] = None
        self._postgres_credentials_expiry: Optional[datetime] = None

        # Cache de credenciais MongoDB para gerenciar renovação
        self._mongodb_credentials: Optional[Dict[str, any]] = None
        self._mongodb_credentials_expiry: Optional[datetime] = None

        # Cache de credenciais Kafka para gerenciar renovação
        self._kafka_credentials: Optional[Dict[str, any]] = None
        self._kafka_credentials_expiry: Optional[datetime] = None

    async def initialize(self):
        """Inicializa clientes Vault e SPIFFE"""
        self.logger.info("initializing_vault_integration")

        try:
            # Initialize SPIFFE manager first (if enabled)
            if self.spiffe_manager and self.config.spiffe_enabled:
                self.logger.info("initializing_spiffe_manager")
                await self.spiffe_manager.initialize()
                self.logger.info("spiffe_manager_initialized")

            # Initialize Vault client
            if self.vault_client and self.config.vault_enabled:
                self.logger.info("initializing_vault_client")
                await self.vault_client.initialize()
                self.logger.info("vault_client_initialized")

                # Start credential renewal task
                self._renewal_task = asyncio.create_task(self.renew_credentials())

            self.logger.info("vault_integration_initialized")

        except (VaultConnectionError, VaultAuthenticationError, SPIFFEConnectionError) as e:
            if not self.config.vault_fail_open:
                self.logger.error("vault_initialization_failed", error=str(e))
                raise
            else:
                self.logger.warning("vault_initialization_failed_failopen", error=str(e))

    async def get_postgres_credentials(self) -> Dict[str, str]:
        """
        Busca credenciais dinâmicas do PostgreSQL no Vault

        Returns:
            Dict com username, password, ttl
        """
        if not self.vault_client or not self.config.vault_enabled:
            # Fallback to config
            return {
                "username": self.config.postgres_user,
                "password": self.config.postgres_password,
                "ttl": 0
            }

        try:
            self.logger.debug("fetching_postgres_credentials")
            creds = await self.vault_client.get_database_credentials("temporal-orchestrator")

            # Armazenar credenciais e expiry para renovação
            self._postgres_credentials = creds
            if creds.get("ttl", 0) > 0:
                self._postgres_credentials_expiry = datetime.utcnow() + timedelta(seconds=creds["ttl"])

            self.logger.info("postgres_credentials_fetched", ttl=creds.get("ttl", 0))
            vault_credentials_fetched_total.labels(credential_type="postgres", status="success").inc()
            return creds

        except Exception as e:
            self.logger.error("postgres_credentials_fetch_failed", error=str(e))
            vault_credentials_fetched_total.labels(credential_type="postgres", status="error").inc()
            if self.config.vault_fail_open:
                # Fallback to config
                return {
                    "username": self.config.postgres_user,
                    "password": self.config.postgres_password,
                    "ttl": 0
                }
            raise

    async def get_mongodb_uri(self) -> str:
        """
        Busca connection string do MongoDB no Vault

        Returns:
            MongoDB URI
        """
        if not self.vault_client or not self.config.vault_enabled:
            return self.config.mongodb_uri

        try:
            self.logger.debug("fetching_mongodb_uri")
            secret = await self.vault_client.read_secret("orchestrator/mongodb")

            if secret and "uri" in secret:
                self.logger.info("mongodb_uri_fetched")
                vault_credentials_fetched_total.labels(credential_type="mongodb", status="success").inc()
                return secret["uri"]
            else:
                self.logger.warning("mongodb_uri_not_found_in_vault")
                return self.config.mongodb_uri

        except Exception as e:
            self.logger.error("mongodb_uri_fetch_failed", error=str(e))
            vault_credentials_fetched_total.labels(credential_type="mongodb", status="error").inc()
            if self.config.vault_fail_open:
                return self.config.mongodb_uri
            raise

    async def get_mongodb_credentials(self) -> Dict[str, str]:
        """
        Busca credenciais dinâmicas do MongoDB no Vault

        Returns:
            Dict com username, password, ttl
        """
        if not self.vault_client or not self.config.vault_enabled:
            # Fallback to config - extract from URI
            uri = self.config.mongodb_uri
            username = ""
            password = ""
            if "://" in uri:
                try:
                    # Parse mongodb://username:password@host format
                    auth_part = uri.split("://")[1].split("@")[0]
                    if ":" in auth_part:
                        username = auth_part.split(":")[0]
                        password = auth_part.split(":")[1] if len(auth_part.split(":")) > 1 else ""
                except (IndexError, ValueError):
                    pass
            return {
                "username": username,
                "password": password,
                "ttl": 0
            }

        try:
            self.logger.debug("fetching_mongodb_credentials")
            creds = await self.vault_client.get_database_credentials("mongodb-orchestrator")

            # Armazenar credenciais e expiry para renovação
            self._mongodb_credentials = creds
            if creds.get("ttl", 0) > 0:
                self._mongodb_credentials_expiry = datetime.utcnow() + timedelta(seconds=creds["ttl"])

            self.logger.info("mongodb_credentials_fetched", ttl=creds.get("ttl", 0))
            vault_credentials_fetched_total.labels(credential_type="mongodb_dynamic", status="success").inc()
            return creds

        except Exception as e:
            self.logger.error("mongodb_credentials_fetch_failed", error=str(e))
            vault_credentials_fetched_total.labels(credential_type="mongodb_dynamic", status="error").inc()
            if self.config.vault_fail_open:
                # Fallback to config
                uri = self.config.mongodb_uri
                username = ""
                password = ""
                if "://" in uri:
                    try:
                        auth_part = uri.split("://")[1].split("@")[0]
                        if ":" in auth_part:
                            username = auth_part.split(":")[0]
                            password = auth_part.split(":")[1] if len(auth_part.split(":")) > 1 else ""
                    except (IndexError, ValueError):
                        pass
                return {
                    "username": username,
                    "password": password,
                    "ttl": 0
                }
            raise

    async def get_redis_password(self) -> Optional[str]:
        """
        Busca senha do Redis no Vault

        Returns:
            Redis password
        """
        if not self.vault_client or not self.config.vault_enabled:
            return self.config.redis_password

        try:
            self.logger.debug("fetching_redis_password")
            secret = await self.vault_client.read_secret("orchestrator/redis")

            if secret and "password" in secret:
                self.logger.info("redis_password_fetched")
                vault_credentials_fetched_total.labels(credential_type="redis", status="success").inc()
                return secret["password"]
            else:
                self.logger.warning("redis_password_not_found_in_vault")
                return self.config.redis_password

        except Exception as e:
            self.logger.error("redis_password_fetch_failed", error=str(e))
            vault_credentials_fetched_total.labels(credential_type="redis", status="error").inc()
            if self.config.vault_fail_open:
                return self.config.redis_password
            raise

    async def get_kafka_credentials(self) -> Dict[str, Optional[str]]:
        """
        Busca credenciais SASL do Kafka no Vault

        Returns:
            Dict com username, password, ttl
        """
        if not self.vault_client or not self.config.vault_enabled:
            return {
                "username": self.config.kafka_sasl_username,
                "password": self.config.kafka_sasl_password,
                "ttl": 0
            }

        try:
            self.logger.debug("fetching_kafka_credentials")
            secret = await self.vault_client.read_secret("orchestrator/kafka")

            if secret:
                # Armazenar credenciais e expiry para renovação
                ttl = secret.get("ttl", 0)
                self._kafka_credentials = secret
                if ttl > 0:
                    self._kafka_credentials_expiry = datetime.utcnow() + timedelta(seconds=ttl)

                self.logger.info("kafka_credentials_fetched", ttl=ttl)
                vault_credentials_fetched_total.labels(credential_type="kafka", status="success").inc()
                return {
                    "username": secret.get("username"),
                    "password": secret.get("password"),
                    "ttl": ttl
                }
            else:
                self.logger.warning("kafka_credentials_not_found_in_vault")
                return {
                    "username": self.config.kafka_sasl_username,
                    "password": self.config.kafka_sasl_password,
                    "ttl": 0
                }

        except Exception as e:
            self.logger.error("kafka_credentials_fetch_failed", error=str(e))
            vault_credentials_fetched_total.labels(credential_type="kafka", status="error").inc()
            if self.config.vault_fail_open:
                return {
                    "username": self.config.kafka_sasl_username,
                    "password": self.config.kafka_sasl_password,
                    "ttl": 0
                }
            raise

    async def renew_credentials(self):
        """
        Background task para renovação de credenciais dinâmicas

        Monitora TTL e renova antes da expiração usando thresholds configurados
        """
        self.logger.info("starting_credential_renewal_task")

        while True:
            try:
                if not self.vault_client or not self.config.vault_enabled:
                    # Sem Vault habilitado, aguardar e continuar
                    await asyncio.sleep(300)  # 5 minutos
                    continue

                # Calcular próximo check baseado em credenciais existentes
                check_interval = await self._calculate_next_check_interval()
                await asyncio.sleep(check_interval)

                self.logger.debug("checking_credential_renewal")

                # 1. Verificar e renovar token Vault
                await self._renew_vault_token_if_needed()

                # 2. Verificar e renovar credenciais PostgreSQL
                await self._renew_postgres_credentials_if_needed()

                # 3. Verificar e renovar credenciais MongoDB
                await self._renew_mongodb_credentials_if_needed()

                # 4. Verificar e renovar credenciais Kafka
                await self._renew_kafka_credentials_if_needed()

                self.logger.debug("credential_renewal_check_complete")
                vault_renewal_task_runs_total.labels(status="success").inc()

            except asyncio.CancelledError:
                self.logger.info("credential_renewal_task_cancelled")
                break
            except Exception as e:
                self.logger.error("credential_renewal_error", error=str(e))
                vault_renewal_task_runs_total.labels(status="error").inc()
                # Em caso de erro, aguardar 60s antes de tentar novamente
                await asyncio.sleep(60)

    async def _calculate_next_check_interval(self) -> int:
        """
        Calcula o próximo intervalo de verificação baseado nas credenciais existentes

        Returns:
            Intervalo em segundos até a próxima verificação
        """
        intervals = []

        # Considerar TTL do token Vault
        if self.vault_client and self.vault_client.token_expiry:
            time_until_expiry = (self.vault_client.token_expiry - datetime.utcnow()).total_seconds()
            if time_until_expiry > 0:
                # Verificar quando atingir o threshold
                check_at = time_until_expiry * (1 - self.config.vault_token_renewal_threshold)
                intervals.append(max(check_at, 60))  # Mínimo 60s

        # Considerar TTL das credenciais PostgreSQL
        if self._postgres_credentials_expiry:
            time_until_expiry = (self._postgres_credentials_expiry - datetime.utcnow()).total_seconds()
            if time_until_expiry > 0:
                # Verificar quando atingir o threshold
                check_at = time_until_expiry * (1 - self.config.vault_db_credentials_renewal_threshold)
                intervals.append(max(check_at, 60))  # Mínimo 60s

        # Considerar TTL das credenciais MongoDB
        if self._mongodb_credentials_expiry:
            time_until_expiry = (self._mongodb_credentials_expiry - datetime.utcnow()).total_seconds()
            if time_until_expiry > 0:
                check_at = time_until_expiry * (1 - self.config.vault_db_credentials_renewal_threshold)
                intervals.append(max(check_at, 60))  # Mínimo 60s

        # Considerar TTL das credenciais Kafka
        if self._kafka_credentials_expiry:
            time_until_expiry = (self._kafka_credentials_expiry - datetime.utcnow()).total_seconds()
            if time_until_expiry > 0:
                check_at = time_until_expiry * (1 - self.config.vault_db_credentials_renewal_threshold)
                intervals.append(max(check_at, 60))  # Mínimo 60s

        # Se não há credenciais para monitorar, verificar a cada 5 minutos
        if not intervals:
            return 300

        # Retornar o menor intervalo (próxima credencial a expirar)
        return int(min(intervals))

    async def _renew_vault_token_if_needed(self):
        """
        Verifica e renova token Vault se necessário
        """
        if not self.vault_client or not self.vault_client.token_expiry:
            return

        time_until_expiry = (self.vault_client.token_expiry - datetime.utcnow()).total_seconds()
        if time_until_expiry <= 0:
            self.logger.warning("vault_token_expired", expired_seconds_ago=abs(time_until_expiry))
            return

        # Calcular percentual de TTL consumido
        # Precisamos estimar TTL original; usamos o último TTL conhecido
        consumed_ratio = 1.0 - (time_until_expiry / self.config.vault_timeout_seconds) if self.config.vault_timeout_seconds > 0 else 1.0

        if consumed_ratio >= (1.0 - self.config.vault_token_renewal_threshold):
            self.logger.info(
                "renewing_vault_token",
                time_until_expiry=time_until_expiry,
                consumed_ratio=consumed_ratio
            )

            try:
                success = await self.vault_client.renew_token()
                if success:
                    self.logger.info("vault_token_renewed_successfully")
                else:
                    self.logger.warning("vault_token_renewal_failed")

            except Exception as e:
                self.logger.error("vault_token_renewal_exception", error=str(e))

    async def _renew_postgres_credentials_if_needed(self):
        """
        Verifica e renova credenciais PostgreSQL se necessário
        """
        if not self._postgres_credentials_expiry:
            # Sem credenciais em cache ou sem TTL
            return

        time_until_expiry = (self._postgres_credentials_expiry - datetime.utcnow()).total_seconds()
        if time_until_expiry <= 0:
            self.logger.warning("postgres_credentials_expired", expired_seconds_ago=abs(time_until_expiry))
            # Buscar novas credenciais imediatamente
            await self._fetch_and_update_postgres_credentials()
            return

        # Verificar se atingiu o threshold de renovação
        original_ttl = self._postgres_credentials.get("ttl", 0) if self._postgres_credentials else 0
        if original_ttl <= 0:
            return

        consumed_ratio = 1.0 - (time_until_expiry / original_ttl)

        if consumed_ratio >= (1.0 - self.config.vault_db_credentials_renewal_threshold):
            self.logger.info(
                "renewing_postgres_credentials",
                time_until_expiry=time_until_expiry,
                consumed_ratio=consumed_ratio
            )

            await self._fetch_and_update_postgres_credentials()

    async def _fetch_and_update_postgres_credentials(self):
        """
        Busca novas credenciais PostgreSQL e atualiza cache interno
        """
        try:
            # Buscar novas credenciais
            new_creds = await self.vault_client.get_database_credentials("temporal-orchestrator")

            # Atualizar cache
            self._postgres_credentials = new_creds
            if new_creds.get("ttl", 0) > 0:
                self._postgres_credentials_expiry = datetime.utcnow() + timedelta(seconds=new_creds["ttl"])

            self.logger.info(
                "postgres_credentials_renewed",
                ttl=new_creds.get("ttl", 0),
                username=new_creds.get("username")
            )
            vault_renewal_task_runs_total.labels(status="success").inc()

            # NOTA: Em um sistema completo, aqui seria necessário atualizar
            # as conexões ativas do PostgreSQL (connection pool do Temporal).
            # Isso requer coordenação com o cliente Temporal e está fora do
            # escopo desta implementação básica. Limitação conhecida: conexões
            # existentes podem continuar usando credenciais expiradas até que o
            # cliente/pool do Temporal seja recriado.
            self.logger.warning(
                "postgres_credentials_renewed_connection_pool_update_required",
                note="Connection pool precisa ser atualizado com novas credenciais"
            )

        except Exception as e:
            self.logger.error("postgres_credentials_renewal_failed", error=str(e))
            vault_renewal_task_runs_total.labels(status="error").inc()
            raise

    async def _renew_mongodb_credentials_if_needed(self):
        """
        Verifica e renova credenciais MongoDB se necessário
        """
        if not self._mongodb_credentials_expiry:
            return

        time_until_expiry = (self._mongodb_credentials_expiry - datetime.utcnow()).total_seconds()
        if time_until_expiry <= 0:
            self.logger.warning("mongodb_credentials_expired", expired_seconds_ago=abs(time_until_expiry))
            await self._fetch_and_update_mongodb_credentials()
            return

        original_ttl = self._mongodb_credentials.get("ttl", 0) if self._mongodb_credentials else 0
        if original_ttl <= 0:
            return

        consumed_ratio = 1.0 - (time_until_expiry / original_ttl)

        if consumed_ratio >= (1.0 - self.config.vault_db_credentials_renewal_threshold):
            self.logger.info(
                "renewing_mongodb_credentials",
                time_until_expiry=time_until_expiry,
                consumed_ratio=consumed_ratio
            )
            await self._fetch_and_update_mongodb_credentials()

    async def _fetch_and_update_mongodb_credentials(self):
        """
        Busca novas credenciais MongoDB e atualiza cache interno
        """
        try:
            new_creds = await self.vault_client.get_database_credentials("mongodb-orchestrator")

            self._mongodb_credentials = new_creds
            if new_creds.get("ttl", 0) > 0:
                self._mongodb_credentials_expiry = datetime.utcnow() + timedelta(seconds=new_creds["ttl"])

            self.logger.info(
                "mongodb_credentials_renewed",
                ttl=new_creds.get("ttl", 0),
                username=new_creds.get("username")
            )
            vault_renewal_task_runs_total.labels(status="success").inc()

            # NOTA: Atualização de connection pool do MongoDB requer
            # recreação do MongoDBClient. Isso deve ser coordenado
            # com o app_state no main.py.
            self.logger.warning(
                "mongodb_credentials_renewed_connection_pool_update_required",
                note="MongoDB connection pool precisa ser atualizado com novas credenciais"
            )

        except Exception as e:
            self.logger.error("mongodb_credentials_renewal_failed", error=str(e))
            vault_renewal_task_runs_total.labels(status="error").inc()
            raise

    async def _renew_kafka_credentials_if_needed(self):
        """
        Verifica e renova credenciais Kafka se necessário
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

        if consumed_ratio >= (1.0 - self.config.vault_db_credentials_renewal_threshold):
            self.logger.info(
                "renewing_kafka_credentials",
                time_until_expiry=time_until_expiry,
                consumed_ratio=consumed_ratio
            )
            await self._fetch_and_update_kafka_credentials()

    async def _fetch_and_update_kafka_credentials(self):
        """
        Busca novas credenciais Kafka e atualiza cache interno
        """
        try:
            secret = await self.vault_client.read_secret("orchestrator/kafka")

            if secret:
                ttl = secret.get("ttl", 0)
                self._kafka_credentials = secret
                if ttl > 0:
                    self._kafka_credentials_expiry = datetime.utcnow() + timedelta(seconds=ttl)

                self.logger.info(
                    "kafka_credentials_renewed",
                    ttl=ttl,
                    username=secret.get("username")
                )
                vault_renewal_task_runs_total.labels(status="success").inc()

                # NOTA: Kafka producer precisa ser recriado com novas credenciais
                self.logger.warning(
                    "kafka_credentials_renewed_producer_update_required",
                    note="Kafka producer precisa ser recriado com novas credenciais"
                )

        except Exception as e:
            self.logger.error("kafka_credentials_renewal_failed", error=str(e))
            vault_renewal_task_runs_total.labels(status="error").inc()
            raise

    async def close(self):
        """Cleanup e revogação de tokens"""
        self.logger.info("closing_vault_integration")

        # Cancel renewal task
        if self._renewal_task:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except asyncio.CancelledError:
                pass

        # Close Vault client
        if self.vault_client:
            await self.vault_client.close()

        # Close SPIFFE manager
        if self.spiffe_manager:
            await self.spiffe_manager.close()

        self.logger.info("vault_integration_closed")
