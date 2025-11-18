"""
GuardVaultClient - Cliente Vault para Guard Agents integrado com neural_hive_security.

Responsável por:
- Autenticação com Vault via SPIFFE JWT-SVID
- Gestão de tokens OPA
- Validação de acesso a secrets
- Auditoria de acessos a secrets
"""

from typing import Optional, Dict
import structlog
from datetime import datetime, timedelta
import time

logger = structlog.get_logger(__name__)


class GuardVaultClient:
    """
    Cliente Vault para Guard Agents com integração SPIFFE.
    """

    def __init__(self, config):
        """
        Inicializa o GuardVaultClient.

        Args:
            config: Configurações do Guard Agents
        """
        self.config = config
        self.vault_addr = config.vault_addr
        self.vault_namespace = config.vault_namespace
        self.fail_open = config.vault_fail_open
        self.vault_client = None
        self.spiffe_manager = None
        self._token_cache = {}

    async def initialize(self) -> None:
        """
        Inicializa conexão com Vault e SPIFFE.

        Raises:
            Exception se falhar e fail_open=False
        """
        try:
            # Importar biblioteca neural_hive_security
            try:
                from neural_hive_security import VaultClient, SPIFFEManager
            except ImportError:
                logger.warning(
                    "guard_vault_client.neural_hive_security_not_available",
                    message="Biblioteca neural_hive_security não disponível"
                )
                if not self.fail_open:
                    raise
                return

            # Inicializar SPIFFE Manager
            self.spiffe_manager = SPIFFEManager()
            await self.spiffe_manager.initialize()

            # Obter JWT-SVID para autenticação
            jwt_svid = await self.spiffe_manager.get_jwt_svid(
                audience=["vault"]
            )

            # Inicializar Vault Client
            self.vault_client = VaultClient(
                addr=self.vault_addr,
                namespace=self.vault_namespace,
                jwt_svid=jwt_svid
            )

            await self.vault_client.authenticate()

            logger.info(
                "guard_vault_client.initialized",
                vault_addr=self.vault_addr,
                namespace=self.vault_namespace
            )

        except Exception as e:
            logger.error(
                "guard_vault_client.initialization_failed",
                error=str(e),
                vault_addr=self.vault_addr
            )
            if not self.fail_open:
                raise

    async def close(self) -> None:
        """
        Fecha conexões com Vault e SPIFFE.
        """
        try:
            if self.vault_client:
                await self.vault_client.close()

            if self.spiffe_manager:
                await self.spiffe_manager.close()

            logger.info("guard_vault_client.closed")

        except Exception as e:
            logger.warning("guard_vault_client.close_failed", error=str(e))

    async def get_opa_token(self) -> str:
        """
        Obtém token para autenticação com OPA.

        Returns:
            Token JWT para OPA

        Raises:
            Exception se falhar e fail_open=False
        """
        start_time = time.time()
        status = "success"

        try:
            # Verificar cache
            cached_token = self._token_cache.get("opa_token")
            if cached_token and cached_token["expires_at"] > datetime.utcnow():
                return cached_token["token"]

            # Obter novo token do Vault
            if not self.vault_client:
                if self.fail_open:
                    logger.warning("guard_vault_client.vault_unavailable")
                    return "mock-opa-token"
                raise Exception("Vault client not initialized")

            token_data = await self.vault_client.get_token(
                role="guard-agents-opa",
                ttl="1h"
            )

            token = token_data["token"]
            lease_duration = token_data.get("lease_duration", 3600)

            # Cachear token
            self._token_cache["opa_token"] = {
                "token": token,
                "expires_at": datetime.utcnow() + timedelta(seconds=lease_duration - 300)
            }

            logger.info("guard_vault_client.opa_token_obtained")

            return token

        except Exception as e:
            status = "error"
            logger.error("guard_vault_client.get_opa_token_failed", error=str(e))
            if self.fail_open:
                return "mock-opa-token"
            raise

        finally:
            # Registrar métricas
            try:
                from src.observability.metrics import vault_requests_total, vault_request_duration_seconds
                duration = time.time() - start_time
                vault_requests_total.labels(operation="get_opa_token", status=status).inc()
                vault_request_duration_seconds.observe(duration)
            except Exception:
                pass  # Não falhar se métricas falharem

    async def get_trivy_credentials(self) -> dict:
        """
        Obtém credenciais para Trivy registry scanning.

        Returns:
            Dicionário com credenciais Trivy

        Raises:
            Exception se falhar e fail_open=False
        """
        start_time = time.time()
        status = "success"

        try:
            if not self.vault_client:
                if self.fail_open:
                    logger.warning("guard_vault_client.vault_unavailable")
                    return {"username": "mock", "password": "mock"}
                raise Exception("Vault client not initialized")

            credentials = await self.vault_client.get_secret(
                path="secret/data/trivy/credentials"
            )

            logger.info("guard_vault_client.trivy_credentials_obtained")

            return {
                "username": credentials["data"]["username"],
                "password": credentials["data"]["password"]
            }

        except Exception as e:
            status = "error"
            logger.error("guard_vault_client.get_trivy_credentials_failed", error=str(e))
            if self.fail_open:
                return {"username": "mock", "password": "mock"}
            raise

        finally:
            # Registrar métricas
            try:
                from src.observability.metrics import vault_requests_total, vault_request_duration_seconds
                duration = time.time() - start_time
                vault_requests_total.labels(operation="get_trivy_credentials", status=status).inc()
                vault_request_duration_seconds.observe(duration)
            except Exception:
                pass  # Não falhar se métricas falharem

    async def validate_secret_access(
        self,
        ticket_id: str,
        secret_path: str
    ) -> bool:
        """
        Valida se ticket tem permissão para acessar secret.

        Args:
            ticket_id: ID do ticket
            secret_path: Caminho do secret no Vault

        Returns:
            True se tem permissão

        Raises:
            Exception se falhar e fail_open=False
        """
        start_time = time.time()
        status = "success"

        try:
            if not self.vault_client:
                if self.fail_open:
                    logger.warning("guard_vault_client.vault_unavailable")
                    return True
                raise Exception("Vault client not initialized")

            # Verificar ACL do secret
            has_access = await self.vault_client.check_access(
                path=secret_path,
                operation="read"
            )

            logger.info(
                "guard_vault_client.secret_access_validated",
                ticket_id=ticket_id,
                secret_path=secret_path,
                has_access=has_access
            )

            return has_access

        except Exception as e:
            status = "error"
            logger.error(
                "guard_vault_client.validate_secret_access_failed",
                error=str(e),
                ticket_id=ticket_id,
                secret_path=secret_path
            )
            if self.fail_open:
                return True
            raise

        finally:
            # Registrar métricas
            try:
                from src.observability.metrics import vault_requests_total, vault_request_duration_seconds
                duration = time.time() - start_time
                vault_requests_total.labels(operation="validate_secret_access", status=status).inc()
                vault_request_duration_seconds.observe(duration)
            except Exception:
                pass  # Não falhar se métricas falharem

    async def audit_secret_access(
        self,
        ticket_id: str,
        secret_path: str,
        action: str
    ) -> None:
        """
        Registra acesso a secrets para auditoria.

        Args:
            ticket_id: ID do ticket
            secret_path: Caminho do secret
            action: Ação realizada (read, write, delete)
        """
        start_time = time.time()
        status = "success"

        try:
            if not self.vault_client:
                logger.warning("guard_vault_client.vault_unavailable")
                return

            # Registrar no audit log do Vault
            await self.vault_client.audit_log(
                event_type="secret_access",
                metadata={
                    "ticket_id": ticket_id,
                    "secret_path": secret_path,
                    "action": action,
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "guard-agents"
                }
            )

            logger.info(
                "guard_vault_client.secret_access_audited",
                ticket_id=ticket_id,
                secret_path=secret_path,
                action=action
            )

        except Exception as e:
            status = "error"
            logger.warning(
                "guard_vault_client.audit_secret_access_failed",
                error=str(e),
                ticket_id=ticket_id
            )

        finally:
            # Registrar métricas
            try:
                from src.observability.metrics import vault_requests_total, vault_request_duration_seconds
                duration = time.time() - start_time
                vault_requests_total.labels(operation="audit_secret_access", status=status).inc()
                vault_request_duration_seconds.observe(duration)
            except Exception:
                pass  # Não falhar se métricas falharem
