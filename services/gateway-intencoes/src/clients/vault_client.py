"""Vault client para obter secrets."""
import os

import hvac
from structlog import get_logger

logger = get_logger()


class VaultClient:
    """Client para obter secrets do HashiCorp Vault."""

    def __init__(self):
        self.vault_addr = os.getenv("VAULT_ADDR", "http://vault.vault.svc.cluster.local:8200")
        self.vault_token = os.getenv("VAULT_TOKEN")
        self.vault_role = os.getenv("VAULT_ROLE", "neural-hive-gateway")
        self.client: hvac.Client | None = None
        self._mount_point = os.getenv("VAULT_MOUNT_POINT", "neural-hive")
        self._initialize()

    def _initialize(self):
        """Inicializar cliente Vault."""
        try:
            self.client = hvac.Client(
                url=self.vault_addr,
                token=self.vault_token,
            )
            if not self.vault_token:
                self.client.auth.kubernetes.login(role=self.vault_role)
            logger.info("vault_client_initialized", vault_addr=self.vault_addr)
        except Exception as e:
            logger.exception("vault_client_init_failed", error=str(e))
            raise

    def get_jwt_secret(self) -> str:
        """Obter JWT secret do Vault."""
        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                path="gateway/jwt",
                mount_point=self._mount_point,
            )
            return response["data"]["data"]["secret"]
        except Exception as e:
            logger.exception("vault_jwt_secret_failed", error=str(e))
            fallback = os.getenv("JWT_SECRET")
            if fallback:
                logger.warning("using_fallback_jwt_secret")
                return fallback
            raise

    def get_api_secret(self, key: str) -> str | None:
        """Obter API secret do Vault.

        Returns:
            O secret solicitado, ou None se não encontrado ou em caso de erro.
        """
        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                path="gateway/api",
                mount_point=self._mount_point,
            )
            return response["data"]["data"].get(key, None)
        except Exception as e:
            logger.exception("vault_api_secret_failed", key=key, error=str(e))
            return None

    def close(self):
        """Fechar conexao Vault."""
        if self.client:
            self.client.close()
