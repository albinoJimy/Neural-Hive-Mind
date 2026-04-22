"""Configuration settings for Hypothesis Library."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Hypothesis Library."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    environment: str = Field(default="dev", description="Environment (dev, staging, prod)")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    service_name: str = Field(default="hypothesis-library", description="Service name")
    service_version: str = Field(default="1.0.0", description="Service version")

    # API Server
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8010, description="API port")
    api_prefix: str = Field(default="/api/v1", description="API prefix")
    cors_origins: list[str] = Field(default=["*"], description="CORS allowed origins")

    # MongoDB
    mongodb_uri: str = Field(
        default="mongodb://mongodb.mongodb.svc.cluster.local:27017",
        description="MongoDB connection URI",
    )
    mongodb_database: str = Field(default="neural_hive", description="MongoDB database name")
    mongodb_hypotheses_collection: str = Field(
        default="hypotheses", description="MongoDB collection for hypotheses"
    )
    mongodb_versions_collection: str = Field(
        default="hypothesis_versions", description="MongoDB collection for hypothesis versions"
    )
    mongodb_max_pool_size: int = Field(
        default=100, description="Maximum MongoDB connections in pool"
    )
    mongodb_min_pool_size: int = Field(
        default=10, description="Minimum MongoDB connections in pool"
    )

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="kafka.kafka.svc.cluster.local:9092", description="Kafka bootstrap servers"
    )
    kafka_hypothesis_events_topic: str = Field(
        default="hypothesis.events", description="Kafka topic for hypothesis events"
    )
    kafka_consumer_group_id: str = Field(
        default="hypothesis-library", description="Kafka consumer group ID"
    )

    # Observability
    otel_endpoint: str = Field(
        default="https://opentelemetry-collector.observability.svc.cluster.local:4317",
        description="OpenTelemetry endpoint",
    )
    otel_tls_verify: bool = Field(default=True, description="Verify TLS certificate")
    prometheus_port: int = Field(default=9090, description="Prometheus metrics port")

    # Hypothesis Configuration
    max_versions_per_hypothesis: int = Field(
        default=50, description="Maximum versions to keep per hypothesis"
    )
    auto_archive_days: int = Field(
        default=180, description="Days after which to auto-archive completed hypotheses"
    )
    require_approval_for_testing: bool = Field(
        default=True, description="Require approval before starting test"
    )
    enable_versioning: bool = Field(default=True, description="Enable hypothesis versioning")

    # Integration endpoints
    experimentation_engine_url: str = Field(
        default="http://optimizer-agents.optimizer-agents.svc.cluster.local:8080",
        description="Experimentation Engine URL",
    )
    experimentation_engine_timeout: int = Field(
        default=30, description="Timeout for Experimentation Engine requests (seconds)"
    )

    @field_validator("api_port", "prometheus_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("max_versions_per_hypothesis", "auto_archive_days")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Value must be positive")
        return v


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
