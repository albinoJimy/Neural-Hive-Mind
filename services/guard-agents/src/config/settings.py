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
    kafka_bootstrap_servers: str = "neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092"
    kafka_consumer_group: str = "guard-agents"
    kafka_incidents_topic: str = "security-incidents"
    kafka_orchestration_incidents_topic: str = "orchestration-incidents"
    kafka_remediation_topic: str = "remediation-actions"
    kafka_tickets_topic: str = "execution.tickets"
    kafka_tickets_validated_topic: str = "execution.tickets.validated"
    kafka_tickets_rejected_topic: str = "execution.tickets.rejected"
    kafka_tickets_pending_approval_topic: str = "execution.tickets.pending_approval"
    kafka_validations_topic: str = "security.validations"
    kafka_auto_offset_reset: str = "earliest"
    kafka_enable_auto_commit: bool = False

    # Service Registry Config (use _GRPC_ to avoid Kubernetes service discovery collision)
    service_registry_grpc_host: str = "service-registry.neural-hive.svc.cluster.local"
    service_registry_grpc_port: int = 50051
    registration_enabled: bool = True
    heartbeat_interval_seconds: int = 30
    capabilities: list[str] = Field(
        default_factory=lambda: [
            "threat-detection",
            "policy-enforcement",
            "incident-classification",
            "auto-remediation",
            "ticket-validation",
            "secrets-scanning",
            "guardrail-enforcement"
        ]
    )

    # MongoDB Config
    mongodb_uri: str = "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin"
    mongodb_database: str = "neural_hive"
    mongodb_incidents_collection: str = "security_incidents"
    mongodb_remediation_collection: str = "remediation_actions"
    mongodb_validations_collection: str = "security_validations"

    # Redis Config
    redis_host: str = "neural-hive-cache.redis-cluster.svc.cluster.local"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # Prometheus Config
    prometheus_url: str = "http://neural-hive-prometheus-kub-prometheus.observability.svc.cluster.local:9090"
    prometheus_query_timeout_seconds: int = 10

    # Alertmanager Config
    alertmanager_url: str = "http://alertmanager.observability.svc.cluster.local:9093"
    alertmanager_webhook_enabled: bool = True

    # Kubernetes Config
    kubernetes_in_cluster: bool = True
    kubernetes_namespace: str = "neural-hive"

    # Self-Healing Engine Config
    self_healing_engine_url: str = "http://self-healing-engine:8080"
    self_healing_engine_grpc_host: str = "self-healing-engine.neural-hive.svc.cluster.local"
    self_healing_engine_grpc_port: int = 50051

    # Detection Thresholds
    mttd_target_seconds: float = 15.0
    mttr_target_seconds: float = 90.0
    anomaly_threshold: float = 0.8
    false_positive_threshold: float = 0.05

    # Enforcement Config
    opa_enforcement_enabled: bool = False
    istio_enforcement_enabled: bool = False
    auto_remediation_enabled: bool = False
    manual_approval_required_for_critical: bool = True

    # OPA Config
    opa_url: str = "http://opa:8181"
    opa_timeout_seconds: int = 5

    # Vault Integration
    vault_enabled: bool = False
    vault_addr: str = "http://vault:8200"
    vault_namespace: str = "neural-hive"
    vault_fail_open: bool = True

    # Trivy Integration
    trivy_enabled: bool = False
    trivy_url: str = "http://trivy:8080"
    trivy_timeout_seconds: int = 30

    # Validation Thresholds
    risk_score_threshold_auto_approve: float = 0.3
    risk_score_threshold_auto_reject: float = 0.9
    require_approval_for_production: bool = True
    require_approval_for_critical_risk: bool = True

    # Guardrails
    guardrails_enabled: bool = True
    guardrails_mode: str = "BLOCKING"
    max_blast_radius_percentage: float = 0.1

    # OpenTelemetry Config
    otel_exporter_otlp_endpoint: str = "http://otel-collector.observability.svc.cluster.local:4317"
    otel_service_name: str = "guard-agents"
    otel_traces_sampler: str = "parentbased_traceidratio"
    otel_traces_sampler_arg: float = 0.1


@lru_cache()
def get_settings() -> Settings:
    """Retorna instância singleton das configurações"""
    return Settings()
