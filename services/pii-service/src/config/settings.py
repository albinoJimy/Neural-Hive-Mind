"""Configurações do PII Service."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações do PII Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8021
    HOST: str = "0.0.0.0"

    # gRPC
    GRPC_PORT: int = 9021
    GRPC_MAX_WORKERS: int = 10

    # MongoDB (INV-13: Audit logging)
    MONGODB_URI: str = "mongodb://mongodb:27017"
    MONGODB_DATABASE: str = "neural_hive"
    PII_AUDIT_LOG_COLLECTION: str = "pii_audit_log"
    AUDIT_LOG_RETENTION_DAYS: int = 90

    # Criptografia (INV-14: Unmask reversível AES-256-GCM)
    ENCRYPTION_KEY_PATH: str | None = None
    # Se None, usa VAULT_ADDR ou gera chave temporária (não recomendado para produção)
    VAULT_ADDR: str | None = None
    VAULT_TOKEN: str | None = None
    VAULT_SECRET_PATH: str = "secret/data/pii-service/encryption-key"

    # JWT Auth
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "RS256"
    JWKS_URL: str | None = None
    JWT_AUTH_REQUIRED: bool = True  # INV-14: Auth required for PII operations

    # PII Detection
    PII_DETECTION_ENABLED: bool = True
    PII_DEFAULT_STRATEGY: str = "MASK_PARTIAL"  # MASK_FULL, MASK_PARTIAL, MASK_REDACT
    PII_ENABLE_SPACY: bool = True
    PII_MIN_CONFIDENCE: float = 0.7

    # Unmask Reversível (INV-14)
    UNMASK_ENABLED: bool = True
    UNMASK_TOKEN_TTL_HOURS: int = 168  # 7 dias
    UNMASK_MAX_ATTEMPTS: int = 3

    # Observabilidade
    OTEL_ENDPOINT: str | None = None
    PROMETHEUS_PORT: int = 9090


@lru_cache
def get_settings() -> Settings:
    """Retorna instância cacheada das configurações."""
    return Settings()
