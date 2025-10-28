from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Self-Healing Engine configuration"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )

    # Service Config
    service_name: str = "self-healing-engine"
    service_version: str = "1.0.0"
    environment: str = "development"
    log_level: str = "INFO"

    # Kafka Config
    kafka_bootstrap_servers: str
    kafka_consumer_group: str = "self-healing-engine"
    kafka_remediation_topic: str = "remediation-actions"
    kafka_auto_offset_reset: str = "earliest"

    # Kubernetes Config
    kubernetes_in_cluster: bool = True
    kubernetes_namespace: str = "neural-hive-resilience"

    # Playbooks Config
    playbooks_dir: str = "./playbooks"

    # OpenTelemetry Config
    otel_exporter_otlp_endpoint: str = "http://tempo:4317"
    otel_service_name: str = "self-healing-engine"


@lru_cache()
def get_settings() -> Settings:
    """Returns singleton settings instance"""
    return Settings()
