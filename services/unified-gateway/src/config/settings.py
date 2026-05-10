"""Configurações da aplicação."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações do Unified Gateway."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 7999
    HOST: str = "0.0.0.0"

    # NLU Service (gRPC corre na porta 8021; 8020 é apenas HTTP/REST do NLU)
    NLU_SERVICE_ADDRESS: str = "nlu-service:8021"
    NLU_SERVICE_TIMEOUT: int = 5

    @property
    def nlu_service_address(self) -> str:
        """Endereço do NLU Service para gRPC."""
        return self.NLU_SERVICE_ADDRESS

    @property
    def nlu_timeout_seconds(self) -> float:
        """Timeout para chamadas gRPC do NLU Service."""
        return float(self.NLU_SERVICE_TIMEOUT)

    # PII Service (gRPC corre na porta 9021; 8021 é apenas HTTP/REST do PII)
    PII_SERVICE_ADDRESS: str = "pii-service:9021"
    PII_SERVICE_TIMEOUT: int = 3

    # Flow Router

    # Rate Limiting
    RATE_LIMIT_DEFAULT: int = 100
    RATE_LIMIT_REDIS_URL: str = "redis://redis:6379/0"

    # Flow Router
    FLOW_AF_GATEWAY: str = "http://gateway-intencoes:8000"
    FLOW_G_GATEWAY: str = "http://requirements-engineering:8010"
    FLOW_H_GATEWAY: str = "http://doc-ingestion:8018"
    FLOW_ROUTER_TIMEOUT: int = 30

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_TOPIC_PREFIX: str = "unified"
    KAFKA_ENABLED: bool = True

    # Auth
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "RS256"
    JWKS_URL: str | None = None
    # JWT obrigatório por defeito; só pode ser desligado explicitamente
    # em ambientes não-produção (ex: development/MVP local).
    JWT_AUTH_REQUIRED: bool = True


@lru_cache
def get_settings() -> Settings:
    """Retorna instância cacheada das configurações."""
    return Settings()
