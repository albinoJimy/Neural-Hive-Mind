"""Configuration settings for Experiment Impact Analyzer."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Experiment Impact Analyzer."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    environment: str = Field(default="dev", description="Environment (dev, staging, prod)")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    service_name: str = Field(default="experiment-impact-analyzer", description="Service name")
    service_version: str = Field(default="1.0.0", description="Service version")

    # API Server
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8020, description="API port")
    api_prefix: str = Field(default="/api/v1", description="API prefix")
    cors_origins: list[str] = Field(default=["*"], description="CORS allowed origins")

    # MongoDB
    mongodb_uri: str = Field(
        default="mongodb://mongodb.mongodb.svc.cluster.local:27017",
        description="MongoDB connection URI",
    )
    mongodb_database: str = Field(default="neural_hive", description="MongoDB database name")
    mongodb_impacts_collection: str = Field(
        default="experiment_impacts", description="MongoDB collection for impact analyses"
    )
    mongodb_experiments_collection: str = Field(
        default="experiments", description="MongoDB collection for experiments"
    )
    mongodb_hypotheses_collection: str = Field(
        default="hypotheses", description="MongoDB collection for hypotheses"
    )
    mongodb_max_pool_size: int = Field(
        default=100, description="Maximum MongoDB connections in pool"
    )
    mongodb_min_pool_size: int = Field(
        default=10, description="Minimum MongoDB connections in pool"
    )

    # MLflow
    mlflow_tracking_uri: str = Field(
        default="http://mlflow.mlflow.svc.cluster.local:5000",
        description="MLflow tracking server URI",
    )

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="kafka.kafka.svc.cluster.local:9092", description="Kafka bootstrap servers"
    )
    kafka_experiment_events_topic: str = Field(
        default="experiment.events", description="Kafka topic for experiment events"
    )
    kafka_consumer_group_id: str = Field(
        default="experiment-impact-analyzer", description="Kafka consumer group ID"
    )

    # Observability
    otel_endpoint: str = Field(
        default="https://opentelemetry-collector.observability.svc.cluster.local:4317",
        description="OpenTelemetry endpoint",
    )
    otel_tls_verify: bool = Field(default=True, description="Verify TLS certificate")
    prometheus_port: int = Field(default=9092, description="Prometheus metrics port")

    # Impact Analysis Configuration
    short_term_window_days: int = Field(
        default=7, description="Days to consider for short-term impact"
    )
    long_term_window_days: int = Field(
        default=90, description="Days to consider for long-term impact"
    )
    min_sample_size_for_impact: int = Field(
        default=100, description="Minimum sample size for impact calculation"
    )
    statistical_significance_threshold: float = Field(
        default=0.95, description="Statistical significance threshold (0-1)"
    )
    correlation_threshold: float = Field(
        default=0.7, description="Minimum correlation coefficient to consider significant"
    )
    enable_long_term_analysis: bool = Field(
        default=True, description="Enable long-term impact analysis"
    )
    enable_correlation_analysis: bool = Field(
        default=True, description="Enable experiment correlation analysis"
    )

    # Integration endpoints
    hypothesis_library_url: str = Field(
        default="http://hypothesis-library.hypothesis-library.svc.cluster.local:8010",
        description="Hypothesis Library URL",
    )
    optimizer_agents_url: str = Field(
        default="http://optimizer-agents.optimizer-agents.svc.cluster.local:8080",
        description="Optimizer Agents URL",
    )
    learning_doc_generator_url: str = Field(
        default="http://learning-doc-generator.learning-doc-generator.svc.cluster.local:8011",
        description="Learning Doc Generator URL",
    )

    @field_validator("api_port", "prometheus_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("short_term_window_days", "long_term_window_days")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Value must be positive")
        return v

    @field_validator("statistical_significance_threshold", "correlation_threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        return v


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
