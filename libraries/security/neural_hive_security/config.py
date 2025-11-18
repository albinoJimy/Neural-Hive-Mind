"""
Configuration models for Neural Hive Security Library
"""

from enum import Enum
from typing import Optional
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


class AuthMethod(str, Enum):
    """Vault authentication methods"""
    KUBERNETES = "kubernetes"
    JWT = "jwt"
    APPROLE = "approle"


class VaultConfig(BaseSettings):
    """Vault client configuration"""

    model_config = ConfigDict(
        env_prefix="VAULT_",
        case_sensitive=False,
        validate_default=True,
    )

    address: str = Field(
        default="http://vault.vault.svc.cluster.local:8200",
        description="Vault server address"
    )
    namespace: str = Field(
        default="",
        description="Vault namespace for multi-tenancy"
    )
    auth_method: AuthMethod = Field(
        default=AuthMethod.KUBERNETES,
        description="Authentication method"
    )
    kubernetes_role: str = Field(
        default="default",
        description="Kubernetes auth role name"
    )
    jwt_path: str = Field(
        default="/var/run/secrets/tokens/vault-token",
        description="Path to JWT token file for JWT auth"
    )
    mount_path_kv: str = Field(
        default="secret",
        description="KV secrets engine mount path"
    )
    mount_path_pki: str = Field(
        default="pki",
        description="PKI engine mount path"
    )
    mount_path_database: str = Field(
        default="database",
        description="Database secrets engine mount path"
    )
    tls_verify: bool = Field(
        default=True,
        description="Enable TLS certificate verification"
    )
    ca_cert_path: Optional[str] = Field(
        default=None,
        description="Path to CA certificate for TLS verification"
    )
    timeout_seconds: int = Field(
        default=5,
        ge=1,
        le=30,
        description="Request timeout in seconds"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts"
    )
    token_ttl_seconds: int = Field(
        default=3600,
        ge=300,
        description="Token TTL in seconds"
    )
    token_renew_threshold: float = Field(
        default=0.8,
        ge=0.5,
        le=0.95,
        description="Token renewal threshold (fraction of TTL)"
    )
    fail_open: bool = Field(
        default=False,
        description="Fail-open on errors (fallback to env vars)"
    )

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """Validate Vault address format"""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Vault address must start with http:// or https://")
        return v


class SPIFFEConfig(BaseSettings):
    """SPIFFE/SPIRE configuration"""

    model_config = ConfigDict(
        env_prefix="SPIFFE_",
        case_sensitive=False,
        validate_default=True,
    )

    workload_api_socket: str = Field(
        default="unix:///run/spire/sockets/agent.sock",
        description="SPIRE Workload API socket path"
    )
    trust_domain: str = Field(
        default="neural-hive.local",
        description="SPIFFE trust domain"
    )
    jwt_audience: str = Field(
        default="vault.neural-hive.local",
        description="Default JWT-SVID audience"
    )
    svid_refresh_threshold: float = Field(
        default=0.8,
        ge=0.5,
        le=0.95,
        description="SVID refresh threshold (fraction of TTL)"
    )
    enable_x509: bool = Field(
        default=False,
        description="Enable X.509-SVID support"
    )
    environment: str = Field(
        default="development",
        description="Environment for SPIFFE fallback policy (development, staging, production)"
    )


class SecuritySettings(BaseSettings):
    """Complete security configuration"""

    model_config = ConfigDict(
        env_prefix="SECURITY_",
        case_sensitive=False,
    )

    vault: VaultConfig = Field(default_factory=VaultConfig)
    spiffe: SPIFFEConfig = Field(default_factory=SPIFFEConfig)

    enable_vault: bool = Field(
        default=False,
        description="Enable Vault integration"
    )
    enable_spiffe: bool = Field(
        default=False,
        description="Enable SPIFFE integration"
    )
    cache_ttl_seconds: int = Field(
        default=300,
        ge=60,
        description="Token cache TTL in seconds"
    )
