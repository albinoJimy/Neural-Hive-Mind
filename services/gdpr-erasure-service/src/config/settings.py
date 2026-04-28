"""
Configuracoes do GDPR Erasure Service
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuracoes centrais do servico"""

    # Service
    service_name: str = "gdpr-erasure-service"
    service_version: str = "1.0.0"
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # API
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8010"))
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "https://neuralhive.ai",
    ]

    # MongoDB (erasure requests)
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_database: str = os.getenv("MONGODB_DATABASE", "nhm_gdpr")

    # Redis (verification tokens, rate limiting)
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_token_ttl: int = int(os.getenv("REDIS_TOKEN_TTL", "3600"))  # 1 hora

    # Kafka (erasure commands to other services)
    kafka_bootstrap_servers: str = os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
    )
    kafka_erasure_commands_topic: str = os.getenv(
        "KAFKA_ERASURE_COMMANDS_TOPIC", "gdpr.erasure.commands"
    )
    kafka_erasure_reports_topic: str = os.getenv(
        "KAFKA_ERASURE_REPORTS_TOPIC", "gdpr.erasure.reports"
    )

    # Security
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production")
    verification_token_salt: str = os.getenv(
        "VERIFICATION_TOKEN_SALT", "nhm-erasure-salt-2024"
    )

    # External Services URLs
    approval_service_url: str = os.getenv(
        "APPROVAL_SERVICE_URL", "http://localhost:8004"
    )
    consensus_engine_url: str = os.getenv(
        "CONSENSUS_ENGINE_URL", "http://localhost:8002"
    )
    execution_ticket_service_url: str = os.getenv(
        "EXECUTION_TICKET_SERVICE_URL", "http://localhost:8009"
    )
    memory_layer_api_url: str = os.getenv(
        "MEMORY_LAYER_API_URL", "http://localhost:8012"
    )

    # OpenTelemetry
    otel_endpoint: str = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
    )
    enable_telemetry: bool = os.getenv("ENABLE_TELEMETRY", "true").lower() == "true"

    # Erasure Settings
    erasure_processing_timeout: int = int(
        os.getenv("ERASURE_PROCESSING_TIMEOUT", "300")
    )  # 5 minutos
    max_concurrent_erasures: int = int(os.getenv("MAX_CONCURRENT_ERASURES", "10"))
    erasure_retention_days: int = int(os.getenv("ERASURE_RETENTION_DAYS", "90"))


@lru_cache
def get_settings() -> Settings:
    """Singleton de settings"""
    return Settings()
