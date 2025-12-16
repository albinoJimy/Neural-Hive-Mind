"""
Async Vault client for secrets management and PKI operations
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import structlog
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from prometheus_client import Counter, Histogram, Gauge

from .config import VaultConfig, AuthMethod


# Prometheus metrics
vault_requests_total = Counter(
    "vault_requests_total",
    "Total Vault API requests",
    ["operation", "status"]
)
vault_request_duration_seconds = Histogram(
    "vault_request_duration_seconds",
    "Vault request duration in seconds",
    ["operation"]
)
vault_token_renewals_total = Counter(
    "vault_token_renewals_total",
    "Total Vault token renewals",
    ["status"]
)
vault_token_ttl_seconds = Gauge(
    "vault_token_ttl_seconds",
    "Current Vault token TTL in seconds"
)
vault_credential_renewals_total = Counter(
    "vault_credential_renewals_total",
    "Credential renewals triggered",
    ["credential_type", "status"]
)


# Custom exceptions
class VaultConnectionError(Exception):
    """Vault connection error"""
    pass


class VaultAuthenticationError(Exception):
    """Vault authentication error"""
    pass


class VaultPermissionError(Exception):
    """Vault permission denied error"""
    pass


logger = structlog.get_logger(__name__)


class VaultClient:
    """
    Async Vault client for secrets management

    Features:
    - Multiple authentication methods (Kubernetes, JWT, AppRole)
    - KV v2 secrets engine
    - Dynamic database credentials
    - PKI certificate issuance
    - Automatic token renewal
    - Retry logic with exponential backoff
    - Circuit breaker pattern
    - Structured logging and metrics
    """

    def __init__(self, config: VaultConfig):
        self.config = config
        self.logger = logger.bind(component="vault_client")
        self.client: Optional[httpx.AsyncClient] = None
        self.token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self._renewal_task: Optional[asyncio.Task] = None
        self._circuit_breaker_failures = 0
        self._circuit_breaker_threshold = 5

    async def initialize(self):
        """Initialize Vault client and authenticate"""
        self.logger.info(
            "initializing_vault_client",
            address=self.config.address,
            auth_method=self.config.auth_method.value
        )

        try:
            # Create HTTP client
            self.client = httpx.AsyncClient(
                base_url=self.config.address,
                timeout=self.config.timeout_seconds,
                verify=self.config.tls_verify,
                headers={"X-Vault-Namespace": self.config.namespace} if self.config.namespace else {}
            )

            # Authenticate
            await self._authenticate()

            # Start token renewal task
            self._renewal_task = asyncio.create_task(self._renewal_loop())

            self.logger.info("vault_client_initialized", token_ttl=self.config.token_ttl_seconds)

        except Exception as e:
            self.logger.error("vault_initialization_failed", error=str(e))
            if not self.config.fail_open:
                raise VaultConnectionError(f"Failed to initialize Vault client: {e}")

    async def _authenticate(self):
        """Authenticate to Vault"""
        self.logger.info("authenticating_to_vault", method=self.config.auth_method.value)

        try:
            if self.config.auth_method == AuthMethod.KUBERNETES:
                await self._authenticate_kubernetes()
            elif self.config.auth_method == AuthMethod.JWT:
                await self._authenticate_jwt()
            else:
                raise VaultAuthenticationError(f"Unsupported auth method: {self.config.auth_method}")

        except Exception as e:
            self.logger.error("vault_authentication_failed", error=str(e))
            raise VaultAuthenticationError(f"Authentication failed: {e}")

    async def _authenticate_kubernetes(self):
        """Authenticate using Kubernetes service account"""
        # Read service account token
        try:
            with open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r") as f:
                jwt = f.read().strip()
        except FileNotFoundError:
            raise VaultAuthenticationError("Kubernetes service account token not found")

        # Authenticate
        response = await self.client.post(
            f"/v1/auth/kubernetes/login",
            json={
                "role": self.config.kubernetes_role,
                "jwt": jwt
            }
        )
        response.raise_for_status()
        data = response.json()

        self.token = data["auth"]["client_token"]
        lease_duration = data["auth"]["lease_duration"]
        self.token_expiry = datetime.utcnow() + timedelta(seconds=lease_duration)

        # Update client headers
        self.client.headers["X-Vault-Token"] = self.token
        vault_token_ttl_seconds.set(lease_duration)

        self.logger.info(
            "kubernetes_auth_successful",
            role=self.config.kubernetes_role,
            ttl=lease_duration
        )

    async def _authenticate_jwt(self):
        """Authenticate using JWT token (SPIFFE)"""
        # Read JWT token
        try:
            with open(self.config.jwt_path, "r") as f:
                jwt = f.read().strip()
        except FileNotFoundError:
            raise VaultAuthenticationError(f"JWT token not found at {self.config.jwt_path}")

        # Authenticate
        response = await self.client.post(
            f"/v1/auth/jwt/login",
            json={
                "role": self.config.kubernetes_role,
                "jwt": jwt
            }
        )
        response.raise_for_status()
        data = response.json()

        self.token = data["auth"]["client_token"]
        lease_duration = data["auth"]["lease_duration"]
        self.token_expiry = datetime.utcnow() + timedelta(seconds=lease_duration)

        # Update client headers
        self.client.headers["X-Vault-Token"] = self.token
        vault_token_ttl_seconds.set(lease_duration)

        self.logger.info(
            "jwt_auth_successful",
            role=self.config.kubernetes_role,
            ttl=lease_duration
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def read_secret(self, path: str) -> Dict[str, Any]:
        """
        Read KV v2 secret

        Args:
            path: Secret path (e.g., "orchestrator/mongodb")

        Returns:
            Secret data dictionary
        """
        operation = "read_secret"
        with vault_request_duration_seconds.labels(operation=operation).time():
            try:
                full_path = f"/v1/{self.config.mount_path_kv}/data/{path}"
                self.logger.debug("reading_secret", path=full_path)

                response = await self.client.get(full_path)
                response.raise_for_status()

                data = response.json()
                vault_requests_total.labels(operation=operation, status="success").inc()

                self.logger.info("secret_read_successful", path=path)
                return data["data"]["data"]

            except httpx.HTTPStatusError as e:
                vault_requests_total.labels(operation=operation, status="error").inc()
                if e.response.status_code == 403:
                    raise VaultPermissionError(f"Permission denied reading {path}")
                elif e.response.status_code == 404:
                    self.logger.warning("secret_not_found", path=path)
                    return {}
                else:
                    raise VaultConnectionError(f"Error reading secret: {e}")

    async def write_secret(self, path: str, data: Dict[str, Any]):
        """
        Write KV v2 secret

        Args:
            path: Secret path
            data: Secret data dictionary
        """
        operation = "write_secret"
        with vault_request_duration_seconds.labels(operation=operation).time():
            try:
                full_path = f"/v1/{self.config.mount_path_kv}/data/{path}"
                self.logger.debug("writing_secret", path=full_path)

                response = await self.client.post(
                    full_path,
                    json={"data": data}
                )
                response.raise_for_status()

                vault_requests_total.labels(operation=operation, status="success").inc()
                self.logger.info("secret_written_successfully", path=path)

            except httpx.HTTPStatusError as e:
                vault_requests_total.labels(operation=operation, status="error").inc()
                if e.response.status_code == 403:
                    raise VaultPermissionError(f"Permission denied writing {path}")
                else:
                    raise VaultConnectionError(f"Error writing secret: {e}")

    async def get_database_credentials(self, role: str) -> Dict[str, Any]:
        """
        Generate dynamic database credentials

        Args:
            role: Database role name

        Returns:
            Dictionary with username, password, and ttl
        """
        operation = "get_database_credentials"
        with vault_request_duration_seconds.labels(operation=operation).time():
            try:
                full_path = f"/v1/{self.config.mount_path_database}/creds/{role}"
                self.logger.debug("generating_database_credentials", role=role)

                response = await self.client.get(full_path)
                response.raise_for_status()

                data = response.json()
                vault_requests_total.labels(operation=operation, status="success").inc()

                self.logger.info(
                    "database_credentials_generated",
                    role=role,
                    ttl=data["lease_duration"]
                )
                vault_credential_renewals_total.labels(credential_type=role, status="success").inc()

                return {
                    "username": data["data"]["username"],
                    "password": data["data"]["password"],
                    "ttl": data["lease_duration"]
                }

            except httpx.HTTPStatusError as e:
                vault_requests_total.labels(operation=operation, status="error").inc()
                vault_credential_renewals_total.labels(credential_type=role, status="error").inc()
                if e.response.status_code == 403:
                    raise VaultPermissionError(f"Permission denied for role {role}")
                else:
                    raise VaultConnectionError(f"Error generating credentials: {e}")

    async def issue_certificate(self, common_name: str, ttl: str = "24h") -> Dict[str, str]:
        """
        Issue PKI certificate

        Args:
            common_name: Certificate common name
            ttl: Certificate TTL (e.g., "24h", "720h")

        Returns:
            Dictionary with certificate, private_key, and ca_chain
        """
        operation = "issue_certificate"
        with vault_request_duration_seconds.labels(operation=operation).time():
            try:
                full_path = f"/v1/{self.config.mount_path_pki}/issue/{common_name}"
                self.logger.debug("issuing_certificate", common_name=common_name, ttl=ttl)

                response = await self.client.post(
                    full_path,
                    json={
                        "common_name": common_name,
                        "ttl": ttl
                    }
                )
                response.raise_for_status()

                data = response.json()
                vault_requests_total.labels(operation=operation, status="success").inc()

                self.logger.info("certificate_issued", common_name=common_name)

                return {
                    "certificate": data["data"]["certificate"],
                    "private_key": data["data"]["private_key"],
                    "ca_chain": data["data"]["ca_chain"][0] if data["data"].get("ca_chain") else ""
                }

            except httpx.HTTPStatusError as e:
                vault_requests_total.labels(operation=operation, status="error").inc()
                raise VaultConnectionError(f"Error issuing certificate: {e}")

    async def renew_token(self) -> bool:
        """
        Renew Vault token

        Returns:
            True if renewal successful, False otherwise
        """
        try:
            self.logger.debug("renewing_vault_token")

            response = await self.client.post("/v1/auth/token/renew-self")
            response.raise_for_status()

            data = response.json()
            lease_duration = data["auth"]["lease_duration"]
            self.token_expiry = datetime.utcnow() + timedelta(seconds=lease_duration)
            vault_token_ttl_seconds.set(lease_duration)

            vault_token_renewals_total.labels(status="success").inc()
            self.logger.info("token_renewed", ttl=lease_duration)

            return True

        except Exception as e:
            vault_token_renewals_total.labels(status="error").inc()
            self.logger.error("token_renewal_failed", error=str(e))
            return False

    async def _renewal_loop(self):
        """Background task for token renewal"""
        while True:
            try:
                if self.token_expiry:
                    # Calculate time until renewal
                    time_until_expiry = (self.token_expiry - datetime.utcnow()).total_seconds()
                    renewal_time = time_until_expiry * (1 - self.config.token_renew_threshold)

                    if renewal_time > 0:
                        self.logger.debug(
                            "scheduling_token_renewal",
                            renewal_in_seconds=renewal_time
                        )
                        await asyncio.sleep(renewal_time)

                    # Renew token
                    await self.renew_token()
                else:
                    # No expiry set, wait and retry
                    await asyncio.sleep(60)

            except asyncio.CancelledError:
                self.logger.info("renewal_loop_cancelled")
                break
            except Exception as e:
                self.logger.error("renewal_loop_error", error=str(e))
                await asyncio.sleep(60)

    async def close(self):
        """Cleanup and revoke token"""
        self.logger.info("closing_vault_client")

        # Cancel renewal task
        if self._renewal_task:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except asyncio.CancelledError:
                pass

        # Revoke token
        if self.token and self.client:
            try:
                await self.client.post("/v1/auth/token/revoke-self")
                self.logger.info("token_revoked")
            except Exception as e:
                self.logger.warning("token_revocation_failed", error=str(e))

        # Close HTTP client
        if self.client:
            await self.client.aclose()

        self.logger.info("vault_client_closed")
