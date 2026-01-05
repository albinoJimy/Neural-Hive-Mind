"""Keycloak Admin Client for token revocation and user management"""
from typing import Dict, Any, Optional
import structlog
from datetime import datetime, timezone
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from prometheus_client import Counter, Histogram

logger = structlog.get_logger()

# Prometheus metrics
keycloak_operations_total = Counter(
    'guard_agents_keycloak_operations_total',
    'Total de operacoes Keycloak Admin',
    ['operation', 'status']
)

keycloak_operation_duration = Histogram(
    'guard_agents_keycloak_operation_duration_seconds',
    'Duracao das operacoes Keycloak Admin',
    ['operation'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0)
)


class KeycloakAdminClient:
    """Cliente para operacoes administrativas do Keycloak"""

    def __init__(
        self,
        keycloak_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        timeout_seconds: int = 10,
        token_cache_ttl_seconds: int = 300
    ):
        self.keycloak_url = keycloak_url.rstrip('/')
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout_seconds
        self.token_cache_ttl = token_cache_ttl_seconds
        self._admin_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    async def connect(self):
        """Inicializa conexao com Keycloak"""
        try:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True
            )
            # Obter token admin inicial
            await self._ensure_token()
            logger.info(
                "keycloak_admin.connected",
                url=self.keycloak_url,
                realm=self.realm
            )
        except Exception as e:
            logger.error("keycloak_admin.connection_failed", error=str(e))
            raise

    async def close(self):
        """Fecha conexao HTTP"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            logger.info("keycloak_admin.connection_closed")

    def is_healthy(self) -> bool:
        """Verifica se cliente esta saudavel"""
        return self._http_client is not None

    async def _ensure_token(self):
        """Garante que temos um token admin valido"""
        now = datetime.now(timezone.utc)

        # Verifica se token ainda e valido (com margem de 30s)
        if (
            self._admin_token
            and self._token_expires_at
            and (self._token_expires_at.timestamp() - now.timestamp()) > 30
        ):
            return

        await self._refresh_admin_token()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException))
    )
    async def _refresh_admin_token(self):
        """Obtem novo token admin via client credentials"""
        token_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"

        try:
            response = await self._http_client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            token_data = response.json()
            self._admin_token = token_data["access_token"]

            # Calcular expiracao (usar token_cache_ttl ou expires_in do token)
            expires_in = min(
                token_data.get("expires_in", self.token_cache_ttl),
                self.token_cache_ttl
            )
            self._token_expires_at = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + expires_in,
                tz=timezone.utc
            )

            logger.debug(
                "keycloak_admin.token_refreshed",
                expires_in=expires_in
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "keycloak_admin.token_refresh_failed",
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except Exception as e:
            logger.error("keycloak_admin.token_refresh_error", error=str(e))
            raise

    def _get_auth_headers(self) -> Dict[str, str]:
        """Retorna headers de autenticacao"""
        return {
            "Authorization": f"Bearer {self._admin_token}",
            "Content-Type": "application/json"
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException))
    )
    async def revoke_user_sessions(self, user_id: str) -> Dict[str, Any]:
        """
        Revoga todas as sessoes ativas de um usuario

        Args:
            user_id: ID do usuario no Keycloak

        Returns:
            Dict com resultado da revogacao
        """
        with keycloak_operation_duration.labels(operation="revoke_sessions").time():
            try:
                await self._ensure_token()

                # Endpoint para logout de todas as sessoes do usuario
                logout_url = (
                    f"{self.keycloak_url}/admin/realms/{self.realm}"
                    f"/users/{user_id}/logout"
                )

                logger.info(
                    "keycloak_admin.revoking_sessions",
                    user_id=user_id
                )

                response = await self._http_client.post(
                    logout_url,
                    headers=self._get_auth_headers()
                )

                if response.status_code == 204:
                    # Sucesso - sem conteudo
                    keycloak_operations_total.labels(
                        operation="revoke_sessions",
                        status="success"
                    ).inc()

                    logger.info(
                        "keycloak_admin.sessions_revoked",
                        user_id=user_id
                    )

                    return {
                        "success": True,
                        "user_id": user_id,
                        "action": "revoke_sessions",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                elif response.status_code == 404:
                    # Usuario nao encontrado
                    keycloak_operations_total.labels(
                        operation="revoke_sessions",
                        status="user_not_found"
                    ).inc()

                    logger.warning(
                        "keycloak_admin.user_not_found",
                        user_id=user_id
                    )

                    return {
                        "success": False,
                        "user_id": user_id,
                        "reason": "User not found",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                else:
                    response.raise_for_status()

            except httpx.HTTPStatusError as e:
                keycloak_operations_total.labels(
                    operation="revoke_sessions",
                    status="error"
                ).inc()

                logger.error(
                    "keycloak_admin.revoke_sessions_failed",
                    user_id=user_id,
                    status_code=e.response.status_code,
                    error=str(e)
                )

                return {
                    "success": False,
                    "user_id": user_id,
                    "reason": f"HTTP error: {e.response.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            except Exception as e:
                keycloak_operations_total.labels(
                    operation="revoke_sessions",
                    status="error"
                ).inc()

                logger.error(
                    "keycloak_admin.revoke_sessions_error",
                    user_id=user_id,
                    error=str(e)
                )

                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException))
    )
    async def disable_user(self, user_id: str) -> Dict[str, Any]:
        """
        Desabilita conta de usuario temporariamente

        Args:
            user_id: ID do usuario no Keycloak

        Returns:
            Dict com resultado da desabilitacao
        """
        with keycloak_operation_duration.labels(operation="disable_user").time():
            try:
                await self._ensure_token()

                # Endpoint para atualizar usuario
                user_url = (
                    f"{self.keycloak_url}/admin/realms/{self.realm}"
                    f"/users/{user_id}"
                )

                logger.info(
                    "keycloak_admin.disabling_user",
                    user_id=user_id
                )

                response = await self._http_client.put(
                    user_url,
                    headers=self._get_auth_headers(),
                    json={"enabled": False}
                )

                if response.status_code == 204:
                    keycloak_operations_total.labels(
                        operation="disable_user",
                        status="success"
                    ).inc()

                    logger.info(
                        "keycloak_admin.user_disabled",
                        user_id=user_id
                    )

                    return {
                        "success": True,
                        "user_id": user_id,
                        "action": "disable_user",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                elif response.status_code == 404:
                    keycloak_operations_total.labels(
                        operation="disable_user",
                        status="user_not_found"
                    ).inc()

                    return {
                        "success": False,
                        "user_id": user_id,
                        "reason": "User not found",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                else:
                    response.raise_for_status()

            except httpx.HTTPStatusError as e:
                keycloak_operations_total.labels(
                    operation="disable_user",
                    status="error"
                ).inc()

                logger.error(
                    "keycloak_admin.disable_user_failed",
                    user_id=user_id,
                    status_code=e.response.status_code
                )

                return {
                    "success": False,
                    "user_id": user_id,
                    "reason": f"HTTP error: {e.response.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            except Exception as e:
                keycloak_operations_total.labels(
                    operation="disable_user",
                    status="error"
                ).inc()

                logger.error(
                    "keycloak_admin.disable_user_error",
                    user_id=user_id,
                    error=str(e)
                )

                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException))
    )
    async def logout_user(self, user_id: str) -> Dict[str, Any]:
        """
        Forca logout de todas as sessoes de um usuario (alias para revoke_user_sessions)

        Args:
            user_id: ID do usuario no Keycloak

        Returns:
            Dict com resultado do logout
        """
        return await self.revoke_user_sessions(user_id)

    async def get_user_sessions(self, user_id: str) -> Dict[str, Any]:
        """
        Obtem sessoes ativas de um usuario

        Args:
            user_id: ID do usuario no Keycloak

        Returns:
            Dict com lista de sessoes
        """
        with keycloak_operation_duration.labels(operation="get_sessions").time():
            try:
                await self._ensure_token()

                sessions_url = (
                    f"{self.keycloak_url}/admin/realms/{self.realm}"
                    f"/users/{user_id}/sessions"
                )

                response = await self._http_client.get(
                    sessions_url,
                    headers=self._get_auth_headers()
                )

                if response.status_code == 200:
                    sessions = response.json()
                    keycloak_operations_total.labels(
                        operation="get_sessions",
                        status="success"
                    ).inc()

                    return {
                        "success": True,
                        "user_id": user_id,
                        "sessions": sessions,
                        "session_count": len(sessions),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                elif response.status_code == 404:
                    keycloak_operations_total.labels(
                        operation="get_sessions",
                        status="user_not_found"
                    ).inc()

                    return {
                        "success": False,
                        "user_id": user_id,
                        "reason": "User not found",
                        "sessions": [],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                else:
                    response.raise_for_status()

            except Exception as e:
                keycloak_operations_total.labels(
                    operation="get_sessions",
                    status="error"
                ).inc()

                logger.error(
                    "keycloak_admin.get_sessions_error",
                    user_id=user_id,
                    error=str(e)
                )

                return {
                    "success": False,
                    "user_id": user_id,
                    "reason": str(e),
                    "sessions": [],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

    async def enable_user(self, user_id: str) -> Dict[str, Any]:
        """
        Reabilita conta de usuario

        Args:
            user_id: ID do usuario no Keycloak

        Returns:
            Dict com resultado da reabilitacao
        """
        with keycloak_operation_duration.labels(operation="enable_user").time():
            try:
                await self._ensure_token()

                user_url = (
                    f"{self.keycloak_url}/admin/realms/{self.realm}"
                    f"/users/{user_id}"
                )

                response = await self._http_client.put(
                    user_url,
                    headers=self._get_auth_headers(),
                    json={"enabled": True}
                )

                if response.status_code == 204:
                    keycloak_operations_total.labels(
                        operation="enable_user",
                        status="success"
                    ).inc()

                    logger.info(
                        "keycloak_admin.user_enabled",
                        user_id=user_id
                    )

                    return {
                        "success": True,
                        "user_id": user_id,
                        "action": "enable_user",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                elif response.status_code == 404:
                    keycloak_operations_total.labels(
                        operation="enable_user",
                        status="user_not_found"
                    ).inc()

                    return {
                        "success": False,
                        "user_id": user_id,
                        "reason": "User not found",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                else:
                    response.raise_for_status()

            except Exception as e:
                keycloak_operations_total.labels(
                    operation="enable_user",
                    status="error"
                ).inc()

                logger.error(
                    "keycloak_admin.enable_user_error",
                    user_id=user_id,
                    error=str(e)
                )

                return {
                    "success": False,
                    "user_id": user_id,
                    "reason": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
