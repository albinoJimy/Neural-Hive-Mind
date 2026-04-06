"""
Neural Hive Security Library

Provides centralized secrets management and workload identity integration
for Neural Hive-Mind services using HashiCorp Vault and SPIFFE/SPIRE.
"""

from .config import (
    AuthMethod,
    SecuritySettings,
    SPIFFEConfig,
    VaultConfig,
)
from .grpc_channel_factory import (
    create_secure_grpc_channel,
    create_secure_grpc_channel_sync,
    get_grpc_metadata_with_jwt,
)

# SEC-008: JWT verification components
from .jwt import (
    JWKValidationError,
    JWKValidationMetrics,
    JWKValidator,
    JWTVerificationError,
    JWTVerificationMetrics,
    JWTVerifier,
    KeyCache,
    VerificationResult,
    get_jwk_validation_metrics,
    get_jwt_verification_metrics,
)
from .spiffe_manager import (
    JWTSVID,
    X509SVID,
    SPIFFEConnectionError,
    SPIFFEFetchError,
    SPIFFEManager,
    TrustBundleValidationError,
)
from .token_cache import (
    CachedToken,
    RefreshStrategy,
    TokenCache,
)
from .vault_client import (
    VaultAuthenticationError,
    VaultClient,
    VaultConnectionError,
    VaultPermissionError,
)

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
    "TrustBundleValidationError",
    "JWTSVID",
    "X509SVID",
    # SEC-008: JWT verification
    "JWKValidator",
    "JWKValidationError",
    "JWTVerifier",
    "JWTVerificationError",
    "VerificationResult",
    "KeyCache",
    "JWKValidationMetrics",
    "JWTVerificationMetrics",
    "get_jwk_validation_metrics",
    "get_jwt_verification_metrics",
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
