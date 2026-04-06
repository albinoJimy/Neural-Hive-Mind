"""
SPIFFE Workload API client for workload identity management
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import grpc
import structlog
from prometheus_client import Counter, Gauge, Histogram

from .config import SPIFFEConfig

# Try to import JWT verification components (SEC-008)
# Import controlado por feature flag para manter backward compatibility
try:
    from .jwt.jwk_validator import JWKValidator
    from .jwt.key_cache import KeyCache
    JWT_COMPONENTS_AVAILABLE = True
except ImportError:
    JWT_COMPONENTS_AVAILABLE = False

# Try to import SPIRE Workload API stubs
try:
    from . import workload_pb2, workload_pb2_grpc
    SPIRE_API_AVAILABLE = True
except ImportError:
    SPIRE_API_AVAILABLE = False


# Prometheus metrics
spiffe_svid_fetch_total = Counter(
    "spiffe_svid_fetch_total",
    "Total SPIFFE SVID fetch attempts",
    ["svid_type", "status"]
)
spiffe_svid_fetch_duration_seconds = Histogram(
    "spiffe_svid_fetch_duration_seconds",
    "SPIFFE SVID fetch duration in seconds",
    ["svid_type"]
)
spiffe_svid_ttl_seconds = Gauge(
    "spiffe_svid_ttl_seconds",
    "TTL (seconds) do SVID retornado",
    ["svid_type"]
)
spiffe_trust_bundle_updates_total = Counter(
    "spiffe_trust_bundle_updates_total",
    "Total de atualizações de trust bundle",
    ["status"]
)


# Custom exceptions
class SPIFFEConnectionError(Exception):
    """SPIFFE connection error"""


class SPIFFEFetchError(Exception):
    """SPIFFE SVID fetch error"""


class TrustBundleValidationError(Exception):
    """Trust bundle JWT validation error (SEC-008)"""


@dataclass
class JWTSVID:
    """JWT-SVID representation"""
    token: str
    spiffe_id: str
    expiry: datetime
    is_placeholder: bool = False


@dataclass
class X509SVID:
    """X.509-SVID representation"""
    certificate: str
    private_key: str
    spiffe_id: str
    ca_bundle: str
    expires_at: datetime
    is_placeholder: bool = False


logger = structlog.get_logger(__name__)


class SPIFFEManager:
    """
    SPIFFE Workload API client

    Features:
    - Fetch JWT-SVIDs with configurable audience
    - X.509-SVID support for certificate-based authentication
    - Automatic SVID refresh before expiration
    - Trust bundle management
    - Integration with VaultClient for JWT auth
    """

    def __init__(self, config: SPIFFEConfig):
        self.config = config
        self.logger = logger.bind(component="spiffe_manager")
        self.channel: grpc.aio.Channel | None = None
        self.stub: Any | None = None  # Workload API stub
        self._jwt_svid_cache: dict[str, JWTSVID] = {}
        self._x509_svid: X509SVID | None = None
        self._trust_bundle: str | None = None
        self._trust_bundle_keys: dict[str, str] = {}  # kid -> public key mapping
        self._refresh_task: asyncio.Task | None = None

        # SEC-008: JWT Verification Components (feature-flagged)
        # Inicializa apenas se enable_jwt_verification=True na configuração
        self._jwk_validator: JWKValidator | None = None
        self._key_cache: KeyCache | None = None

        if config.enable_jwt_verification and JWT_COMPONENTS_AVAILABLE:
            self._jwk_validator = JWKValidator(strict_mode=True)
            # Cache com TTL de 5 minutos (configurável via JWT_CACHE_TTL_SECONDS)
            cache_ttl = getattr(config, "jwt_cache_ttl_seconds", 300)
            self._key_cache = KeyCache(ttl_seconds=cache_ttl)
            self.logger.info(
                "jwt_verification_enabled",
                cache_ttl_seconds=cache_ttl,
                strict_mode=True
            )
        elif config.enable_jwt_verification and not JWT_COMPONENTS_AVAILABLE:
            self.logger.warning(
                "jwt_verification_requested_but_components_unavailable",
                message="JWT components not available - install PyJWT and python-jose"
            )

    async def initialize(self):
        """Initialize SPIFFE Workload API connection"""
        self.logger.info(
            "initializing_spiffe_manager",
            socket=self.config.workload_api_socket,
            trust_domain=self.config.trust_domain
        )

        try:
            # Connect to Workload API (Unix domain socket)
            self.channel = grpc.aio.insecure_channel(
                self.config.workload_api_socket,
                options=[
                    ("grpc.default_authority", self.config.trust_domain),
                ]
            )

            # Create Workload API stub if available
            if SPIRE_API_AVAILABLE:
                self.stub = workload_pb2_grpc.SpiffeWorkloadAPIStub(self.channel)
                self.logger.info("spire_workload_api_stub_created")
            else:
                self.logger.warning(
                    "spire_api_stubs_unavailable",
                    message="SPIRE Workload API stubs not available, using fallback mode"
                )

            # Verify connectivity by fetching initial JWT-SVID
            await self.fetch_jwt_svid(self.config.jwt_audience)

            # Fetch trust bundle
            await self.get_trust_bundle()

            # Start refresh loop
            self._refresh_task = asyncio.create_task(self._refresh_loop())

            self.logger.info("spiffe_manager_initialized")

        except Exception as e:
            self.logger.error("spiffe_initialization_failed", error=str(e))
            raise SPIFFEConnectionError(f"Failed to initialize SPIFFE manager: {e}")

    async def fetch_jwt_svid(self, audience: str, ttl_seconds: int | None = None) -> JWTSVID:
        """
        Fetch JWT-SVID for specified audience using SPIRE Workload API

        Args:
            audience: JWT audience (e.g., "vault.neural-hive.local")
            ttl_seconds: Desired TTL for the JWT-SVID in seconds (defaults to config.jwt_ttl_seconds)

        Returns:
            JWTSVID object
        """
        operation = "jwt_svid"
        with spiffe_svid_fetch_duration_seconds.labels(svid_type=operation).time():
            try:
                # Check cache first
                if audience in self._jwt_svid_cache:
                    cached = self._jwt_svid_cache[audience]
                    if cached.expiry > datetime.now(timezone.utc) + timedelta(minutes=5):
                        self.logger.debug("using_cached_jwt_svid", audience=audience)
                        return cached

                desired_ttl = ttl_seconds or self.config.jwt_ttl_seconds
                self.logger.debug("fetching_jwt_svid_from_spire", audience=audience, ttl=desired_ttl)

                # Attempt to fetch from SPIRE Workload API
                if SPIRE_API_AVAILABLE and self.stub:
                    try:
                        # Create JWT-SVID request
                        request = workload_pb2.JWTSVIDRequest(audience=[audience], ttl=desired_ttl)

                        # Call Workload API
                        response = await self.stub.FetchJWTSVID(request)

                        if response.svids:
                            svid_data = response.svids[0]
                            spiffe_id = svid_data.spiffe_id
                            token = svid_data.svid
                            expiry = datetime.utcfromtimestamp(svid_data.expires_at)

                            jwt_svid = JWTSVID(
                                token=token,
                                spiffe_id=spiffe_id,
                                expiry=expiry
                            )

                            # Cache the SVID
                            self._jwt_svid_cache[audience] = jwt_svid

                            spiffe_svid_fetch_total.labels(svid_type=operation, status="success").inc()
                            spiffe_svid_ttl_seconds.labels(svid_type=operation).set(
                                (expiry - datetime.now(timezone.utc)).total_seconds()
                            )
                            self.logger.info(
                                "jwt_svid_fetched_from_spire",
                                audience=audience,
                                spiffe_id=spiffe_id,
                                expiry=expiry.isoformat()
                            )

                            return jwt_svid
                        raise SPIFFEFetchError("No SVIDs returned from Workload API")

                    except Exception as e:
                        self.logger.warning(
                            "spire_workload_api_fetch_failed",
                            audience=audience,
                            error=str(e),
                            fallback="Using environment/file fallback"
                        )
                        # Fall through to fallback mode

                # Fallback: Read from environment or file if SPIRE unavailable
                import os
                spiffe_id = os.getenv("SPIFFE_ID", f"spiffe://{self.config.trust_domain}/default")
                desired_ttl = ttl_seconds or self.config.jwt_ttl_seconds

                # Try reading JWT from file (injected by SPIRE agent via volume mount)
                jwt_token_path = os.getenv("SPIFFE_JWT_TOKEN_PATH", "/var/run/secrets/tokens/spiffe-jwt")
                try:
                    with open(jwt_token_path) as f:
                        token = f.read().strip()
                    # Parse expiry from JWT (simplified - in production decode properly)
                    expiry = datetime.now(timezone.utc) + timedelta(seconds=desired_ttl)
                except FileNotFoundError:
                    # Check environment - fail in production/staging if no real SVID
                    if self.config.environment in ["production", "staging"]:
                        spiffe_svid_fetch_total.labels(svid_type=operation, status="error").inc()
                        self.logger.error(
                            "spiffe_unavailable_in_production",
                            environment=self.config.environment,
                            audience=audience,
                            message="SPIFFE placeholders disabled in production/staging"
                        )
                        raise SPIFFEFetchError(
                            f"SPIFFE unavailable in {self.config.environment}; placeholders disabled for security"
                        )

                    # Development: generate placeholder with warning
                    self.logger.warning(
                        "jwt_token_file_not_found_using_placeholder",
                        path=jwt_token_path,
                        environment=self.config.environment,
                        warning="Using placeholder SVID in development - not for production"
                    )
                    token = f"eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.placeholder.{audience}"
                    expiry = datetime.now(timezone.utc) + timedelta(seconds=desired_ttl)

                jwt_svid = JWTSVID(
                    token=token,
                    spiffe_id=spiffe_id,
                    expiry=expiry,
                    is_placeholder=True  # Mark as placeholder
                )

                # Cache the SVID
                self._jwt_svid_cache[audience] = jwt_svid

                spiffe_svid_fetch_total.labels(svid_type=operation, status="success").inc()
                spiffe_svid_ttl_seconds.labels(svid_type=operation).set(
                    (expiry - datetime.now(timezone.utc)).total_seconds()
                )
                self.logger.info(
                    "jwt_svid_fetched_fallback",
                    audience=audience,
                    spiffe_id=spiffe_id,
                    expiry=expiry.isoformat(),
                    is_placeholder=True,
                    environment=self.config.environment
                )

                return jwt_svid

            except Exception as e:
                spiffe_svid_fetch_total.labels(svid_type=operation, status="error").inc()
                self.logger.error("jwt_svid_fetch_failed", audience=audience, error=str(e))
                raise SPIFFEFetchError(f"Failed to fetch JWT-SVID: {e}")

    async def fetch_x509_svid(self) -> X509SVID:
        """
        Fetch X.509-SVID

        Returns:
            X509SVID object with certificate and private key
        """
        if not self.config.enable_x509:
            raise SPIFFEFetchError("X.509-SVID support is disabled")

        operation = "x509_svid"
        with spiffe_svid_fetch_duration_seconds.labels(svid_type=operation).time():
            try:
                # Check cache
                if self._x509_svid:
                    if self._x509_svid.expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
                        self.logger.debug("using_cached_x509_svid")
                        return self._x509_svid

                self.logger.debug("fetching_x509_svid_from_spire")

                # Attempt to fetch from SPIRE Workload API
                if SPIRE_API_AVAILABLE and self.stub:
                    try:
                        # Create X.509-SVID request
                        request = workload_pb2.X509SVIDRequest()

                        # Call Workload API (streaming response)
                        response_stream = self.stub.FetchX509SVID(request)

                        # Get first response from stream
                        async for response in response_stream:
                            if response.svids:
                                svid_data = response.svids[0]
                                spiffe_id = svid_data.spiffe_id
                                certificate = svid_data.x509_svid.decode("utf-8")
                                private_key = svid_data.x509_svid_key.decode("utf-8")
                                expiry = datetime.utcfromtimestamp(svid_data.expires_at)
                                bundle_pem = svid_data.bundle.decode("utf-8") if svid_data.bundle else (self._trust_bundle or "")

                                x509_svid = X509SVID(
                                    certificate=certificate,
                                    private_key=private_key,
                                    spiffe_id=spiffe_id,
                                    ca_bundle=bundle_pem,
                                    expires_at=expiry
                                )

                                self._x509_svid = x509_svid

                                # Also update trust bundle from response
                                if svid_data.bundle:
                                    self._trust_bundle = bundle_pem

                                spiffe_svid_fetch_total.labels(svid_type=operation, status="success").inc()
                                spiffe_svid_ttl_seconds.labels(svid_type=operation).set(
                                    (expiry - datetime.now(timezone.utc)).total_seconds()
                                )
                                self.logger.info(
                                    "x509_svid_fetched_from_spire",
                                    spiffe_id=spiffe_id,
                                    expiry=expiry.isoformat()
                                )

                                return x509_svid
                            break

                        raise SPIFFEFetchError("No X.509-SVIDs returned from Workload API")

                    except Exception as e:
                        self.logger.warning(
                            "spire_x509_fetch_failed",
                            error=str(e),
                            fallback="Using placeholder"
                        )
                        # Fall through to fallback

                # Fallback mode - check environment
                import os

                # Fail in production/staging if no real X.509-SVID
                if self.config.environment in ["production", "staging"]:
                    spiffe_svid_fetch_total.labels(svid_type=operation, status="error").inc()
                    self.logger.error(
                        "x509_svid_unavailable_in_production",
                        environment=self.config.environment,
                        message="X.509-SVID placeholders disabled in production/staging"
                    )
                    raise SPIFFEFetchError(
                        f"X.509-SVID unavailable in {self.config.environment}; placeholders disabled for security"
                    )

                # Development: generate placeholder with warning
                spiffe_id = os.getenv("SPIFFE_ID", f"spiffe://{self.config.trust_domain}/default")

                self.logger.warning(
                    "x509_svid_using_placeholder",
                    environment=self.config.environment,
                    warning="Using placeholder X.509-SVID in development - not for production"
                )

                x509_svid = X509SVID(
                    certificate="-----BEGIN CERTIFICATE-----\nplaceholder\n-----END CERTIFICATE-----",
                    private_key="-----BEGIN PRIVATE KEY-----\nplaceholder\n-----END PRIVATE KEY-----",
                    spiffe_id=spiffe_id,
                    ca_bundle="-----BEGIN CERTIFICATE-----\nplaceholder CA\n-----END CERTIFICATE-----",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                    is_placeholder=True  # Mark as placeholder
                )

                self._x509_svid = x509_svid

                spiffe_svid_fetch_total.labels(svid_type=operation, status="success").inc()
                spiffe_svid_ttl_seconds.labels(svid_type=operation).set(
                    (self._x509_svid.expires_at - datetime.now(timezone.utc)).total_seconds()
                )
                self.logger.info(
                    "x509_svid_fetched_fallback",
                    spiffe_id=spiffe_id,
                    is_placeholder=True,
                    environment=self.config.environment
                )

                return x509_svid

            except Exception as e:
                spiffe_svid_fetch_total.labels(svid_type=operation, status="error").inc()
                self.logger.error("x509_svid_fetch_failed", error=str(e))
                raise SPIFFEFetchError(f"Failed to fetch X.509-SVID: {e}")

    async def get_trust_bundle(self) -> str:
        """
        Retrieve trust bundle for JWT verification from SPIRE

        Returns:
            Trust bundle (PEM-encoded certificates or JWKS)
        """
        try:
            # Check cache
            if self._trust_bundle:
                return self._trust_bundle

            self.logger.debug("fetching_trust_bundle_from_spire")

            # Attempt to fetch from SPIRE Workload API
            if SPIRE_API_AVAILABLE and self.stub:
                try:
                    # Fetch JWT bundles (streaming)
                    response_stream = self.stub.FetchJWTBundles(None)

                    async for bundle_response in response_stream:
                        # Extract trust bundle from response
                        # In real implementation, parse JWKS format
                        if hasattr(bundle_response, "bundles"):
                            # Extract keys from JWKS
                            trust_domain_bundle = bundle_response.bundles.get(self.config.trust_domain)
                            if trust_domain_bundle:
                                # Store both PEM and parsed keys
                                self._trust_bundle = str(trust_domain_bundle)

                                # Parse JWKS to extract public keys for JWT validation
                                try:
                                    import json
                                    jwks_data = json.loads(trust_domain_bundle)
                                    for key in jwks_data.get("keys", []):
                                        kid = key.get("kid")
                                        if kid:
                                            self._trust_bundle_keys[kid] = key
                                except:
                                    pass

                                self.logger.info(
                                    "trust_bundle_fetched_from_spire",
                                    trust_domain=self.config.trust_domain,
                                    num_keys=len(self._trust_bundle_keys)
                                )
                                spiffe_trust_bundle_updates_total.labels(status="success").inc()

                                return self._trust_bundle
                        break

                except Exception as e:
                    self.logger.warning(
                        "spire_trust_bundle_fetch_failed",
                        error=str(e),
                        fallback="Using placeholder"
                    )

            # Fallback: use placeholder
            trust_bundle = "-----BEGIN CERTIFICATE-----\nplaceholder CA\n-----END CERTIFICATE-----"

            self._trust_bundle = trust_bundle
            spiffe_trust_bundle_updates_total.labels(status="success").inc()
            self.logger.info("trust_bundle_fetched_fallback")

            return trust_bundle

        except Exception as e:
            self.logger.error("trust_bundle_fetch_failed", error=str(e))
            spiffe_trust_bundle_updates_total.labels(status="error").inc()
            raise SPIFFEFetchError(f"Failed to fetch trust bundle: {e}")

    def get_trust_bundle_keys(self) -> dict[str, str]:
        """
        Get parsed public keys from trust bundle for JWT validation

        SEC-008: Se enable_jwt_verification=True, valida JWKS com
        JWKValidator antes de retornar as chaves. Usa KeyCache com TTL
        para evitar validações repetidas.

        Returns:
            Dictionary mapping key ID to public key

        Raises:
            TrustBundleValidationError: Se validação JWKS falhar
        """
        # Se validação JWT não está activada, retorna keys directamente
        if self._jwk_validator is None or self._key_cache is None:
            self.logger.debug("jwt_verification_disabled_returning_raw_keys")
            return self._trust_bundle_keys.copy()

        # Verificar cache primeiro
        cached_keys = {}
        keys_to_validate = {}

        # Tentar obter do cache
        for kid, key_data in self._trust_bundle_keys.items():
            cached_key = self._key_cache.get(kid)
            if cached_key is not None:
                cached_keys[kid] = cached_key
            else:
                keys_to_validate[kid] = key_data

        # Validar chaves não em cache
        if keys_to_validate:
            self.logger.debug(
                "validating_jwks_keys",
                cached_count=len(cached_keys),
                to_validate_count=len(keys_to_validate)
            )

            # Construir JWKS para validação
            jwks_to_validate = {"keys": list(keys_to_validate.values())}
            validation_result = self._jwk_validator.validate_jwks(jwks_to_validate)

            # Log de resultado
            self.logger.info(
                "jwks_validation_completed",
                valid_count=validation_result.get("valid_count", 0),
                invalid_count=validation_result.get("invalid_count", 0),
                total_count=validation_result.get("total_count", 0)
            )

            # Se há chaves inválidas, levantar erro (modo strict)
            invalid_count = validation_result.get("invalid_count", 0)
            if invalid_count > 0:
                invalid_ids = validation_result.get("invalid_key_ids", [])
                raise TrustBundleValidationError(
                    f"Trust bundle contém {invalid_count} chave(s) inválida(s): "
                    f"{invalid_ids}. Modo strict activado - rejeitando keys."
                )

            # Armazenar chaves validadas no cache
            for kid, key_data in keys_to_validate.items():
                self._key_cache.put(kid, key_data)

        # Retornar chaves em cache + validadas
        result = {**cached_keys, **keys_to_validate}
        self.logger.debug("trust_bundle_keys_returned", count=len(result))

        return result

    def get_key_cache(self) -> KeyCache | None:
        """
        Retorna a instância de KeyCache para gestão manual de chaves.

        SEC-008: Permite acesso externo ao cache para operações como
        invalidação, limpeza de expirados, e consulta de estatísticas.

        Returns:
            Instância de KeyCache ou None se JWT verification desactivado

        Example:
            cache = spiffe_manager.get_key_cache()
            if cache:
                # Limpar chaves expiradas
                cache.cleanup_expired()
                # Obter estatísticas
                stats = cache.get_stats()
        """
        return self._key_cache

    def get_jwk_validator(self) -> JWKValidator | None:
        """
        Retorna a instância de JWKValidator para validação manual de JWKs.

        SEC-008: Permite validação de JWKs externos ao trust bundle.

        Returns:
            Instância de JWKValidator ou None se JWT verification desactivado

        Example:
            validator = spiffe_manager.get_jwk_validator()
            if validator:
                is_valid = validator.validate(jwk_data)
                if not is_valid:
                    errors = validator.get_errors()
        """
        return self._jwk_validator

    async def _refresh_loop(self):
        """Background task for SVID refresh"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                # Refresh JWT-SVIDs
                for audience, svid in list(self._jwt_svid_cache.items()):
                    time_until_expiry = (svid.expiry - datetime.now(timezone.utc)).total_seconds()
                    refresh_threshold = self.config.jwt_ttl_seconds * self.config.svid_refresh_threshold

                    if time_until_expiry < refresh_threshold:
                        self.logger.info("refreshing_jwt_svid", audience=audience)
                        try:
                            await self.fetch_jwt_svid(audience)
                        except SPIFFEFetchError as e:
                            # In production, refresh failure is critical
                            if self.config.environment in ["production", "staging"]:
                                self.logger.error(
                                    "jwt_svid_refresh_failed_production",
                                    environment=self.config.environment,
                                    audience=audience,
                                    error=str(e)
                                )
                                # Re-raise to alert on critical failure
                                raise
                            # Development: log warning but continue
                            self.logger.warning(
                                "jwt_svid_refresh_failed_development",
                                audience=audience,
                                error=str(e)
                            )

                # Refresh X.509-SVID if enabled
                if self.config.enable_x509 and self._x509_svid:
                    time_until_expiry = (self._x509_svid.expires_at - datetime.now(timezone.utc)).total_seconds()
                    refresh_threshold = 86400 * self.config.svid_refresh_threshold  # Default 24 hours * 0.8

                    if time_until_expiry < refresh_threshold:
                        self.logger.info("refreshing_x509_svid")
                        try:
                            await self.fetch_x509_svid()
                        except SPIFFEFetchError as e:
                            # In production, refresh failure is critical
                            if self.config.environment in ["production", "staging"]:
                                self.logger.error(
                                    "x509_svid_refresh_failed_production",
                                    environment=self.config.environment,
                                    error=str(e)
                                )
                                raise
                            self.logger.warning(
                                "x509_svid_refresh_failed_development",
                                error=str(e)
                            )

            except asyncio.CancelledError:
                self.logger.info("refresh_loop_cancelled")
                break
            except Exception as e:
                self.logger.error("refresh_loop_error", error=str(e))

    async def close(self):
        """Close SPIFFE Workload API connection"""
        self.logger.info("closing_spiffe_manager")

        # Cancel refresh task
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

        # Close channel
        if self.channel:
            await self.channel.close()

        self.logger.info("spiffe_manager_closed")
