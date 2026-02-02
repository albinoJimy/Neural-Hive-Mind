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
    kafka_incident_topic: str = "orchestration.incidents"
    kafka_incident_group: str = "self-healing-incidents"
    schemas_base_path: str = "./schemas"

    # Kubernetes Config
    kubernetes_in_cluster: bool = True
    kubernetes_namespace: str = "neural-hive-resilience"

    # Playbooks Config
    playbooks_dir: str = "./playbooks"
    playbook_timeout_seconds: int = 300

    # Service Registry
    service_registry_host: str = "service-registry.neural-hive-execution.svc.cluster.local"
    service_registry_port: int = 50051
    service_registry_timeout_seconds: int = 3

    # OpenTelemetry Config
    otel_exporter_otlp_endpoint: str = "http://tempo:4317"
    otel_service_name: str = "self-healing-engine"

    # Execution Ticket Service Config
    execution_ticket_service_url: str = "http://execution-ticket-service.neural-hive.svc.cluster.local:8000"
    execution_ticket_service_timeout: int = 30
    execution_ticket_circuit_breaker_threshold: int = 5
    execution_ticket_circuit_breaker_reset_seconds: int = 60

    # Orchestrator Dynamic gRPC Config
    orchestrator_grpc_host: str = "orchestrator-dynamic.neural-hive.svc.cluster.local"
    orchestrator_grpc_port: int = 50052
    orchestrator_grpc_use_tls: bool = True
    orchestrator_grpc_timeout_seconds: int = 10

    # OPA Policy Engine Config
    opa_host: str = "opa.neural-hive-governance.svc.cluster.local"
    opa_port: int = 8181
    opa_timeout_seconds: int = 5
    opa_enabled: bool = True
    opa_fail_open: bool = True  # Allow actions if OPA is unavailable
    opa_cache_ttl_seconds: int = 60
    opa_circuit_breaker_enabled: bool = True
    opa_circuit_breaker_failure_threshold: int = 5
    opa_circuit_breaker_reset_timeout: int = 30
    opa_retry_attempts: int = 3
    opa_max_concurrent_evaluations: int = 20

    # Chaos Engineering Config
    chaos_enabled: bool = False
    chaos_max_concurrent_experiments: int = 3
    chaos_default_timeout_seconds: int = 600
    chaos_require_opa_approval: bool = True
    chaos_blast_radius_limit: int = 5


@lru_cache()
def get_settings() -> Settings:
    """Returns singleton settings instance"""
    return Settings()
