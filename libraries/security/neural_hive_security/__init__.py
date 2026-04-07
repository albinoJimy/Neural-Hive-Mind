"""
Neural Hive Security Library

Provides centralized secrets management and workload identity integration
for Neural Hive-Mind services using HashiCorp Vault and SPIFFE/SPIRE.

SEC-008: Added JWT/JWK verification components for trust bundle validation.
"""

from .vault_client import (
    VaultClient,
    VaultConnectionError,
    VaultAuthenticationError,
    VaultPermissionError,
)
from .spiffe_manager import (
    SPIFFEManager,
    SPIFFEConnectionError,
    SPIFFEFetchError,
    JWTSVID,
    X509SVID,
)
from .token_cache import (
    TokenCache,
    CachedToken,
    RefreshStrategy,
)
from .config import (
    VaultConfig,
    SPIFFEConfig,
    SecuritySettings,
    AuthMethod,
)
from .grpc_channel_factory import (
    create_secure_grpc_channel,
    create_secure_grpc_channel_sync,
    get_grpc_metadata_with_jwt,
)

# SEC-008: JWT verification components
try:
    from .jwt import (
        JWKValidator,
        JWKValidationError,
        JWTVerifier,
        JWTVerificationError,
        VerificationResult,
        KeyCache,
        JWTVerificationMetrics,
        JWKValidationMetrics,
        get_jwt_verification_metrics,
        get_jwk_validation_metrics,
    )

    JWT_MODULE_AVAILABLE = True
except ImportError:
    JWT_MODULE_AVAILABLE = False
    JWKValidator = None
    JWKValidationError = None
    JWTVerifier = None
    JWTVerificationError = None
    VerificationResult = None
    KeyCache = None
    JWTVerificationMetrics = None
    JWKValidationMetrics = None
    get_jwt_verification_metrics = None
    get_jwk_validation_metrics = None

__version__ = "1.0.0"

__all__ = [
    # Vault client
    "VaultClient",
    "VaultConnectionError",
    "VaultAuthenticationError",
    "VaultPermissionError",
    # SPIFFE manager
    "SPIFFEManager",
    "SPIFFEConnectionError",
    "SPIFFEFetchError",
    "JWTSVID",
    "X509SVID",
    # Token cache
    "TokenCache",
    "CachedToken",
    "RefreshStrategy",
    # Configuration
    "VaultConfig",
    "SPIFFEConfig",
    "SecuritySettings",
    "AuthMethod",
    # gRPC channel factory
    "create_secure_grpc_channel",
    "create_secure_grpc_channel_sync",
    "get_grpc_metadata_with_jwt",
]

# SEC-008: Adicionar componentes JWT às exportações se disponíveis
if JWT_MODULE_AVAILABLE:
    __all__.extend(
        [
            "JWKValidator",
            "JWKValidationError",
            "JWTVerifier",
            "JWTVerificationError",
            "VerificationResult",
            "KeyCache",
            "JWTVerificationMetrics",
            "JWKValidationMetrics",
            "get_jwt_verification_metrics",
            "get_jwk_validation_metrics",
        ]
    )
