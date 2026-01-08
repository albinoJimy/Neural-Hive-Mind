"""
Neural Hive Security Library

Provides centralized secrets management and workload identity integration
for Neural Hive-Mind services using HashiCorp Vault and SPIFFE/SPIRE.
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
