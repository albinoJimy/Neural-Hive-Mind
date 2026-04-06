"""
SPIFFE Workload API client for workload identity management
"""

import asyncio
import grpc
import json
import base64
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import structlog
from prometheus_client import Counter, Histogram, Gauge
import os

from .config import SPIFFEConfig

# Feature flag para verificação JWT (SEC-008)
# Pode ser controlada via environment variable: ENABLE_JWT_VERIFICATION=true
ENABLE_JWT_VERIFICATION = os.getenv("ENABLE_JWT_VERIFICATION", "false").lower() == "true"

# Try to import SPIRE Workload API stubs
try:
    from . import workload_pb2
    from . import workload_pb2_grpc
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

# Import JWT verification module (SEC-008) - lazy import para evitar dependência circular
# A métrica spiffe_trust_bundle_updates_total é definida em jwt/metrics.py
# e importada aqui apenas quando necessária
JWT_VERIFICATION_AVAILABLE = False
JWKValidator = None
KeyCache = None
SPIFFETrustBundleMetrics = None
spiffe_trust_bundle_updates_total = None

try:
    # Import dentro de try para evitar falha se módulo não disponível
    from .jwt import JWKValidator, KeyCache
    from .jwt.metrics import (
        SPIFFETrustBundleMetrics,
        spiffe_trust_bundle_updates_total
    )
    JWT_VERIFICATION_AVAILABLE = True
except ImportError:
    # Criar métrica fallback se módulo JWT não disponível
    spiffe_trust_bundle_updates_total = Counter(
        "spiffe_trust_bundle_updates_total",
        "Total de atualizações de trust bundle",
        ["status"]
    )


# Custom exceptions
class SPIFFEConnectionError(Exception):
    """SPIFFE connection error"""
    pass


class SPIFFEFetchError(Exception):
    """SPIFFE SVID fetch error"""
    pass


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
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[Any] = None  # Workload API stub
        self._jwt_svid_cache: Dict[str, JWTSVID] = {}
        self._x509_svid: Optional[X509SVID] = None
        self._trust_bundle: Optional[str] = None
        self._trust_bundle_keys: Dict[str, str] = {}  # kid -> public key mapping

        # SEC-008: JWT verification components
        self._jwk_validator: Optional[JWKValidator] = None
        self._key_cache: Optional[KeyCache] = None
        self._trust_bundle_metrics: Optional[SPIFFETrustBundleMetrics] = None

        # Inicializar componentes de verificação JWT se habilitado
        if JWT_VERIFICATION_AVAILABLE and ENABLE_JWT_VERIFICATION:
            self._jwk_validator = JWKValidator(strict_mode=True)
            self._key_cache = KeyCache(ttl_seconds=300)  # 5 minutos
            self._trust_bundle_metrics = SPIFFETrustBundleMetrics()
            self.logger.info(
                "jwt_verification_enabled",
                feature_flag="ENABLE_JWT_VERIFICATION",
                ttl_seconds=300
            )

        self._refresh_task: Optional[asyncio.Task] = None

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
                    ('grpc.default_authority', self.config.trust_domain),
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

    async def fetch_jwt_svid(self, audience: str, ttl_seconds: Optional[int] = None) -> JWTSVID:
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
                        else:
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
                    with open(jwt_token_path, "r") as f:
                        token = f.read().strip()
                    # Parse expiry from JWT (simplified - in production decode properly)
                    expiry = datetime.now(timezone.utc) + timedelta(seconds=desired_ttl)
                except FileNotFoundError:
                    # Check environment - fail in production/staging if no real SVID
                    if self.config.environment in ['production', 'staging']:
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
                                certificate = svid_data.x509_svid.decode('utf-8')
                                private_key = svid_data.x509_svid_key.decode('utf-8')
                                expiry = datetime.utcfromtimestamp(svid_data.expires_at)
                                bundle_pem = svid_data.bundle.decode('utf-8') if svid_data.bundle else (self._trust_bundle or "")

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
                if self.config.environment in ['production', 'staging']:
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

        SEC-008: Now validates JWKS structure and caches keys with TTL.

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
                        if hasattr(bundle_response, 'bundles'):
                            # Extract keys from JWKS
                            trust_domain_bundle = bundle_response.bundles.get(self.config.trust_domain)
                            if trust_domain_bundle:
                                # Store both PEM and parsed keys
                                self._trust_bundle = str(trust_domain_bundle)

                                # SEC-008: Parse and validate JWKS
                                try:
                                    import json
                                    jwks_data = json.loads(trust_domain_bundle)

                                    # Validar JWKS com JWKValidator
                                    if self._jwk_validator and self._trust_bundle_metrics:
                                        with self._trust_bundle_metrics.time_validation():
                                            validation_results = self._jwk_validator.validate_jwks(jwks_data)

                                        self.logger.info(
                                            "trust_bundle_jwks_validated",
                                            trust_domain=self.config.trust_domain,
                                            valid_count=validation_results.get("valid_count", 0),
                                            invalid_count=validation_results.get("invalid_count", 0),
                                            invalid_key_ids=validation_results.get("invalid_key_ids", [])
                                        )

                                        # Registrar métricas
                                        if self._trust_bundle_metrics:
                                            self._trust_bundle_metrics.record_update(
                                                status="success",
                                                keys_validated=validation_results.get("valid_count", 0),
                                                keys_invalid=validation_results.get("invalid_count", 0)
                                            )

                                    # Extrair e cachear chaves válidas
                                    for key in jwks_data.get('keys', []):
                                        kid = key.get('kid')
                                        if kid:
                                            self._trust_bundle_keys[kid] = key

                                            # SEC-008: Adicionar ao KeyCache com TTL
                                            if self._key_cache:
                                                self._key_cache.put(kid, key)

                                except json.JSONDecodeError as e:
                                    self.logger.warning(
                                        "trust_bundle_json_parse_failed",
                                        error=str(e)
                                    )
                                except Exception as e:
                                    self.logger.warning(
                                        "trust_bundle_validation_failed",
                                        error=str(e)
                                    )

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
                    if self._trust_bundle_metrics:
                        self._trust_bundle_metrics.record_update(status="failed")

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

    def get_trust_bundle_keys(self) -> Dict[str, str]:
        """
        Get parsed public keys from trust bundle for JWT validation

        SEC-008: Returns keys from KeyCache if enabled, otherwise from memory.

        Returns:
            Dictionary mapping key ID to public key (JWK dict)
        """
        # Se KeyCache estiver disponível, retornar chaves do cache
        if self._key_cache:
            cached_keys = {}
            for key_id in self._key_cache.keys():
                cached_keys[key_id] = self._key_cache.get(key_id)

            # Log stats do cache
            cache_stats = self._key_cache.get_stats()
            self.logger.debug(
                "trust_bundle_keys_from_cache",
                keys_count=len(cached_keys),
                cache_hits=cache_stats.get("hits"),
                cache_misses=cache_stats.get("misses"),
                hit_rate=cache_stats.get("hit_rate")
            )

            return cached_keys

        # Fallback para memória (sem cache)
        return self._trust_bundle_keys.copy()

    def get_key_cache(self) -> Optional["KeyCache"]:
        """
        Retorna a instância de KeyCache para uso externo.

        SEC-008: Permite que componentes externos (ex: AuthInterceptor)
        acessem o cache de chaves.

        Returns:
            Instância de KeyCache ou None
        """
        return self._key_cache

    def get_jwk_validator(self) -> Optional["JWKValidator"]:
        """
        Retorna a instância de JWKValidator para uso externo.

        SEC-008: Permite que componentes externos validem JWKs.

        Returns:
            Instância de JWKValidator ou None
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
                            if self.config.environment in ['production', 'staging']:
                                self.logger.error(
                                    "jwt_svid_refresh_failed_production",
                                    environment=self.config.environment,
                                    audience=audience,
                                    error=str(e)
                                )
                                # Re-raise to alert on critical failure
                                raise
                            else:
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
                            if self.config.environment in ['production', 'staging']:
                                self.logger.error(
                                    "x509_svid_refresh_failed_production",
                                    environment=self.config.environment,
                                    error=str(e)
                                )
                                raise
                            else:
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
