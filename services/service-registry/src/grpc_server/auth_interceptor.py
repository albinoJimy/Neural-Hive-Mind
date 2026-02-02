"""
gRPC server interceptor para verificação de tokens SPIFFE JWT-SVID
"""

import grpc
from grpc import aio
import structlog
import json
import base64
from typing import Callable, Any, Dict, Optional
from datetime import datetime
from prometheus_client import Counter, REGISTRY

# Import security library (optional)
try:
    from neural_hive_security import SPIFFEManager
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    SPIFFEManager = None

# Try to import JWT library for validation
try:
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    JWT_LIB_AVAILABLE = True
except ImportError:
    JWT_LIB_AVAILABLE = False


logger = structlog.get_logger(__name__)


def _get_or_create_counter(name: str, description: str, labelnames=None):
    """Get existing counter or create new one to avoid duplicate registration errors"""
    try:
        return Counter(name, description, labelnames or [])
    except ValueError:
        return REGISTRY._names_to_collectors.get(name)


# Metrics
grpc_auth_attempts_total = _get_or_create_counter(
    "grpc_auth_attempts_total",
    "Total gRPC authentication attempts",
    ["method", "status"]
)
grpc_auth_failures_total = _get_or_create_counter(
    "grpc_auth_failures_total",
    "Total gRPC authentication failures",
    ["method", "reason"]
)


class SPIFFEAuthInterceptor(aio.ServerInterceptor):
    """
    gRPC server interceptor para autenticação via SPIFFE JWT-SVID

    Verifica tokens JWT-SVID em metadata de requisições gRPC
    e extrai SPIFFE ID para autorização
    """

    def __init__(self, spiffe_manager: "SPIFFEManager", settings):
        self.spiffe_manager = spiffe_manager
        self.settings = settings
        self.logger = logger.bind(component="spiffe_auth_interceptor")

        # Allowed SPIFFE IDs por método (simplificado)
        self.allowed_spiffe_ids = {
            "Register": [
                f"spiffe://{settings.SPIFFE_TRUST_DOMAIN}/ns/neural-hive-execution/sa/worker-agents"
            ],
            "Deregister": [
                f"spiffe://{settings.SPIFFE_TRUST_DOMAIN}/ns/neural-hive-execution/sa/worker-agents"
            ],
            "Heartbeat": [
                f"spiffe://{settings.SPIFFE_TRUST_DOMAIN}/ns/neural-hive-execution/sa/worker-agents"
            ],
            "DiscoverAgents": [
                f"spiffe://{settings.SPIFFE_TRUST_DOMAIN}/ns/neural-hive/sa/orchestrator-dynamic",
                f"spiffe://{settings.SPIFFE_TRUST_DOMAIN}/ns/neural-hive-execution/sa/worker-agents"
            ],
            "Health": ["*"],  # Allow all for health checks
            "Check": ["*"],   # gRPC health check method
            "Watch": ["*"],   # gRPC health watch method
        }

        # Methods to skip authentication entirely (health checks, reflection, etc.)
        self.unauthenticated_methods = {
            "Health",
            "Check",
            "Watch",
        }
        # Method prefixes to skip authentication (e.g., grpc.health.v1.Health/)
        self.unauthenticated_prefixes = [
            "/grpc.health.v1.Health/",
            "/grpc.reflection.v1alpha.ServerReflection/",
        ]

    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Any],
        handler_call_details: grpc.HandlerCallDetails
    ) -> grpc.RpcMethodHandler:
        """
        Intercept gRPC service calls para autenticação
        """
        full_method = handler_call_details.method
        method = full_method.split("/")[-1]

        # Skip auth if SPIFFE_VERIFY_PEER is disabled
        if not self.settings.SPIFFE_VERIFY_PEER:
            return await continuation(handler_call_details)

        # Skip auth for health checks and reflection by method name
        if method in self.unauthenticated_methods:
            return await continuation(handler_call_details)

        # Skip auth for health/reflection by full method path prefix
        for prefix in self.unauthenticated_prefixes:
            if full_method.startswith(prefix):
                return await continuation(handler_call_details)

        # Extract authorization header
        metadata = dict(handler_call_details.invocation_metadata)
        auth_header = metadata.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            grpc_auth_attempts_total.labels(method=method, status="missing_token").inc()
            grpc_auth_failures_total.labels(method=method, reason="missing_token").inc()
            self.logger.warning("missing_authorization_header", method=method)
            return self._unauthenticated()

        # Extract token
        token = auth_header[7:]  # Remove "Bearer "

        # Verify JWT-SVID
        try:
            # Validate and decode JWT-SVID
            spiffe_id = await self._validate_jwt_svid(token, method)

            if not spiffe_id:
                grpc_auth_failures_total.labels(method=method, reason="invalid_token").inc()
                self.logger.warning("invalid_spiffe_token", method=method)
                return self._unauthenticated()

            # Check authorization
            if not self._is_authorized(spiffe_id, method):
                grpc_auth_failures_total.labels(method=method, reason="unauthorized").inc()
                self.logger.warning("unauthorized_spiffe_id", method=method, spiffe_id=spiffe_id)
                return self._permission_denied()

            grpc_auth_attempts_total.labels(method=method, status="success").inc()
            self.logger.debug("authenticated", method=method, spiffe_id=spiffe_id)

            # Add SPIFFE ID to context for use in servicer
            # handler_call_details context would be updated here

            return await continuation(handler_call_details)

        except Exception as e:
            grpc_auth_failures_total.labels(method=method, reason="verification_error").inc()
            self.logger.error("auth_verification_failed", method=method, error=str(e))
            return self._unauthenticated()

    async def _validate_jwt_svid(self, token: str, method: str) -> Optional[str]:
        """
        Validate JWT-SVID token and extract SPIFFE ID

        Args:
            token: JWT-SVID token
            method: gRPC method name for logging

        Returns:
            SPIFFE ID from token's sub claim, or None if invalid
        """
        try:
            # If PyJWT is available and SPIFFE manager is available, use proper validation
            if JWT_LIB_AVAILABLE and self.spiffe_manager:
                # Step 1: Decode JWT header to get kid (key ID)
                unverified_header = jwt.get_unverified_header(token)
                kid = unverified_header.get('kid')

                # Step 2: Get trust bundle keys from SPIFFE manager
                trust_bundle_keys = self.spiffe_manager.get_trust_bundle_keys()

                if not trust_bundle_keys:
                    self.logger.warning(
                        "no_trust_bundle_keys_available",
                        method=method,
                        fallback="Attempting trust bundle fetch"
                    )
                    # Try to fetch trust bundle
                    await self.spiffe_manager.get_trust_bundle()
                    trust_bundle_keys = self.spiffe_manager.get_trust_bundle_keys()

                # Step 3: Find matching public key
                public_key = None
                if kid and kid in trust_bundle_keys:
                    jwk = trust_bundle_keys[kid]
                    # Convert JWK to PEM for PyJWT
                    public_key = self._jwk_to_pem(jwk)
                elif trust_bundle_keys:
                    # Try first available key if no kid match
                    first_key = list(trust_bundle_keys.values())[0]
                    public_key = self._jwk_to_pem(first_key)

                if not public_key:
                    self.logger.warning("no_public_key_found", method=method, kid=kid)
                    return None

                # Step 4: Verify and decode JWT
                decoded = jwt.decode(
                    token,
                    public_key,
                    algorithms=['RS256', 'ES256', 'ES384'],
                    options={
                        'verify_signature': True,
                        'verify_exp': True,
                        'verify_nbf': True,
                        'verify_iat': True,
                        'require_exp': True,
                    }
                )

                # Step 5: Validate claims
                # Check issuer (should be trust domain)
                iss = decoded.get('iss')
                if iss and not iss.startswith(f'https://{self.settings.SPIFFE_TRUST_DOMAIN}'):
                    self.logger.warning("invalid_issuer", method=method, issuer=iss)
                    return None

                # Check audience (should match expected audience)
                aud = decoded.get('aud', [])
                expected_aud = f"spiffe://{self.settings.SPIFFE_TRUST_DOMAIN}"
                if isinstance(aud, list):
                    if expected_aud not in aud:
                        self.logger.debug("audience_mismatch", method=method, aud=aud, expected=expected_aud)
                        # Don't reject - some implementations use different audience
                elif aud != expected_aud:
                    self.logger.debug("audience_mismatch", method=method, aud=aud, expected=expected_aud)

                # Step 6: Extract SPIFFE ID from sub claim
                spiffe_id = decoded.get('sub')

                if not spiffe_id or not spiffe_id.startswith('spiffe://'):
                    self.logger.warning("invalid_spiffe_id_in_token", method=method, sub=spiffe_id)
                    return None

                self.logger.info(
                    "jwt_svid_validated",
                    method=method,
                    spiffe_id=spiffe_id,
                    exp=decoded.get('exp')
                )

                return spiffe_id

            else:
                # Fallback: In production/staging, fail-closed when JWT verification is not available
                environment = getattr(self.settings, 'ENVIRONMENT', 'development').lower()

                if environment in ('production', 'staging'):
                    self.logger.error(
                        "jwt_validation_unavailable_production",
                        jwt_lib=JWT_LIB_AVAILABLE,
                        spiffe_manager=self.spiffe_manager is not None,
                        method=method,
                        environment=environment,
                        msg="Fail-closed: JWT library not available in production/staging"
                    )
                    # Fail-closed: reject the request
                    return None

                # Development/test fallback: Decode without verification (not secure - for testing only)
                self.logger.warning(
                    "jwt_validation_unavailable_dev_fallback",
                    jwt_lib=JWT_LIB_AVAILABLE,
                    spiffe_manager=self.spiffe_manager is not None,
                    method=method,
                    environment=environment,
                    msg="INSECURE: Using unverified JWT parsing in non-production environment"
                )

                # Decode without verification to get claims
                payload_part = token.split('.')[1]
                # Add padding if needed
                padding = 4 - len(payload_part) % 4
                if padding != 4:
                    payload_part += '=' * padding

                payload_bytes = base64.urlsafe_b64decode(payload_part)
                payload = json.loads(payload_bytes)

                # Extract SPIFFE ID from sub
                spiffe_id = payload.get('sub')

                # Check expiry
                exp = payload.get('exp')
                if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
                    self.logger.warning("token_expired", method=method, exp=exp)
                    return None

                if spiffe_id and spiffe_id.startswith('spiffe://'):
                    return spiffe_id

                return None

        except jwt.ExpiredSignatureError:
            self.logger.warning("jwt_expired", method=method)
            return None
        except jwt.InvalidTokenError as e:
            self.logger.warning("jwt_invalid", method=method, error=str(e))
            return None
        except Exception as e:
            self.logger.error("jwt_validation_error", method=method, error=str(e))
            return None

    def _jwk_to_pem(self, jwk: Dict) -> Optional[str]:
        """
        Convert JWK to PEM format for JWT verification

        Args:
            jwk: JSON Web Key

        Returns:
            PEM-encoded public key or None
        """
        try:
            # This is a simplified implementation
            # In production, use a proper JWK library like python-jose
            import jwt.algorithms as jwt_algs

            # Use PyJWT's JWK conversion
            if hasattr(jwt_algs, 'RSAAlgorithm'):
                algo = jwt_algs.RSAAlgorithm(jwt_algs.RSAAlgorithm.SHA256)
                public_key = algo.from_jwk(json.dumps(jwk))

                pem = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
                return pem.decode('utf-8')

            return None

        except Exception as e:
            self.logger.error("jwk_to_pem_conversion_failed", error=str(e))
            return None

    def _is_authorized(self, spiffe_id: str, method: str) -> bool:
        """
        Verifica se SPIFFE ID está autorizado para o método

        Args:
            spiffe_id: SPIFFE ID do cliente
            method: Nome do método gRPC

        Returns:
            True se autorizado
        """
        allowed = self.allowed_spiffe_ids.get(method, [])

        if "*" in allowed:
            return True

        return spiffe_id in allowed

    def _unauthenticated(self) -> grpc.RpcMethodHandler:
        """Retorna handler para UNAUTHENTICATED"""
        def abort(ignored_request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or missing authentication token")
        return grpc.unary_unary_rpc_method_handler(abort)

    def _permission_denied(self) -> grpc.RpcMethodHandler:
        """Retorna handler para PERMISSION_DENIED"""
        def abort(ignored_request, context):
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Access denied for this SPIFFE ID")
        return grpc.unary_unary_rpc_method_handler(abort)
