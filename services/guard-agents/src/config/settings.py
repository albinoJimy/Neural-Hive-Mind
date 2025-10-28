from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações do Guard Agents via variáveis de ambiente"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )

    # Service Config
    service_name: str = "guard-agents"
    service_version: str = "1.0.0"
    environment: str = "development"
    log_level: str = "INFO"

    # Kafka Config
    kafka_bootstrap_servers: str
    kafka_consumer_group: str = "guard-agents"
    kafka_incidents_topic: str = "security-incidents"
    kafka_orchestration_incidents_topic: str = "orchestration-incidents"
    kafka_remediation_topic: str = "remediation-actions"
    kafka_auto_offset_reset: str = "earliest"
    kafka_enable_auto_commit: bool = False

    # Service Registry Config
    service_registry_host: str
    service_registry_port: int = 50051
    registration_enabled: bool = True
    heartbeat_interval_seconds: int = 30
    capabilities: list[str] = Field(
        default_factory=lambda: [
            "threat-detection",
            "policy-enforcement",
            "incident-classification",
            "auto-remediation"
        ]
    )

    # MongoDB Config
    mongodb_uri: str
    mongodb_database: str = "neural_hive"
    mongodb_incidents_collection: str = "security_incidents"
    mongodb_remediation_collection: str = "remediation_actions"

    # Redis Config
    redis_host: str
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # Prometheus Config
    prometheus_url: str
    prometheus_query_timeout_seconds: int = 10

    # Alertmanager Config
    alertmanager_url: str
    alertmanager_webhook_enabled: bool = True

    # Kubernetes Config
    kubernetes_in_cluster: bool = True
    kubernetes_namespace: str = "neural-hive-resilience"

    # Self-Healing Engine Config
    self_healing_engine_url: str
    self_healing_engine_grpc_host: str
    self_healing_engine_grpc_port: int = 50051

    # Detection Thresholds
    mttd_target_seconds: float = 15.0
    mttr_target_seconds: float = 90.0
    anomaly_threshold: float = 0.8
    false_positive_threshold: float = 0.05

    # Enforcement Config
    opa_enforcement_enabled: bool = True
    istio_enforcement_enabled: bool = True
    auto_remediation_enabled: bool = True
    manual_approval_required_for_critical: bool = True

    # OPA Config
    opa_url: str = "http://opa:8181"
    opa_timeout_seconds: int = 5

    # OpenTelemetry Config
    otel_exporter_otlp_endpoint: str
    otel_service_name: str = "guard-agents"
    otel_traces_sampler: str = "parentbased_traceidratio"
    otel_traces_sampler_arg: float = 0.1


@lru_cache()
def get_settings() -> Settings:
    """Retorna instância singleton das configurações"""
    return Settings()
