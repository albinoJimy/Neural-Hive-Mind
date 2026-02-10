from functools import lru_cache
from typing import Optional
from pydantic import Field, model_validator
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
    allow_insecure_http_endpoints: bool = Field(
        default=False,
        description="Allow insecure HTTP endpoints in production (for internal cluster communication)"
    )

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
    prometheus_url: str = "https://prometheus-server.monitoring.svc.cluster.local:9090"
    prometheus_tls_verify: bool = Field(default=True, description="Verificar certificado TLS do Prometheus")
    prometheus_ca_bundle: Optional[str] = Field(default=None, description="Caminho para CA bundle do Prometheus")
    prometheus_query_timeout_seconds: int = 10

    # Alertmanager Config
    alertmanager_url: str = "https://alertmanager.monitoring.svc.cluster.local:9093"
    alertmanager_tls_verify: bool = Field(default=True, description="Verificar certificado TLS do Alertmanager")
    alertmanager_ca_bundle: Optional[str] = Field(default=None, description="Caminho para CA bundle do Alertmanager")
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

    # OPA Policy Paths (without data. prefix - OPA endpoint /v1/data/{path} adds it automatically)
    opa_security_policy_path: str = "neuralhive/guard/security_policies/result"
    opa_compliance_policy_path: str = "neuralhive/guard/compliance_policies/result"
    opa_resource_policy_path: str = "neuralhive/guard/resource_policies/result"

    # Security Policy Thresholds
    max_vulnerability_severity: str = "HIGH"
    require_signed_images: bool = True
    require_network_policies_production: bool = True
    allowed_capabilities: list[str] = Field(
        default_factory=lambda: ["NET_BIND_SERVICE"]
    )

    # Compliance Policy Thresholds
    required_regulations: list[str] = Field(
        default_factory=lambda: ["GDPR"]
    )
    max_retention_days: int = 365
    max_pii_retention_days: int = 180
    require_encryption_at_rest: bool = True
    require_audit_logging: bool = True
    min_audit_retention_days: int = 365

    # Resource Policy Thresholds
    max_cpu_per_container: str = "4000m"
    max_memory_per_container: str = "8Gi"
    min_replicas_production: int = 2
    max_replicas: int = 100
    require_hpa_production: bool = True
    min_cpu_utilization_percent: int = 20
    min_memory_utilization_percent: int = 20

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
    otel_exporter_otlp_endpoint: str = "https://opentelemetry-collector.observability.svc.cluster.local:4317"
    otel_tls_verify: bool = Field(default=True, description="Verificar certificado TLS do OTEL Collector")
    otel_ca_bundle: Optional[str] = Field(default=None, description="Caminho para CA bundle do OTEL Collector")
    otel_service_name: str = "guard-agents"
    otel_traces_sampler: str = "parentbased_traceidratio"
    otel_traces_sampler_arg: float = 0.1

    # MLflow Config
    mlflow_tracking_uri: str = "https://mlflow.mlflow.svc.cluster.local:5000"
    mlflow_tls_verify: bool = Field(default=True, description="Verificar certificado TLS do MLflow")
    mlflow_ca_bundle: Optional[str] = Field(default=None, description="Caminho para CA bundle do MLflow")

    # Keycloak Admin Config
    keycloak_url: str = "https://keycloak.auth.svc.cluster.local:8443"
    keycloak_tls_verify: bool = Field(default=True, description="Verificar certificado TLS do Keycloak")
    keycloak_ca_bundle: Optional[str] = Field(default=None, description="Caminho para CA bundle do Keycloak")
    keycloak_realm: str = "neural-hive"
    keycloak_admin_client_id: str = "guard-agents-admin"
    keycloak_admin_client_secret: str | None = Field(default=None)
    keycloak_admin_timeout_seconds: int = 10
    keycloak_token_cache_ttl_seconds: int = 300

    # MongoDB Post-Mortems Config
    mongodb_postmortems_collection: str = "incident_postmortems"

    # Anomaly Detector Config
    anomaly_detector_enabled: bool = True
    anomaly_detector_model_type: str = "isolation_forest"
    anomaly_detector_contamination: float = 0.05

    # ITSM Integration Config
    itsm_enabled: bool = False
    itsm_type: str = Field(default="webhook", description="ITSM type: servicenow, jira, pagerduty, opsgenie, webhook")
    itsm_url: Optional[str] = Field(default=None, description="ITSM API base URL")
    itsm_api_key: Optional[str] = Field(default=None, description="ITSM API key or token")
    itsm_username: Optional[str] = Field(default=None, description="ITSM username for basic auth")
    itsm_password: Optional[str] = Field(default=None, description="ITSM password for basic auth")
    itsm_timeout_seconds: int = 30

    # ChaosMesh Config
    chaosmesh_enabled: bool = False
    chaosmesh_namespace: str = "chaos-testing"

    # Script Execution Config
    script_execution_enabled: bool = False
    script_executor_namespace: str = "neural-hive"
    script_executor_service_account: str = "guard-agents-executor"
    script_executor_default_image: str = "alpine:3.18"
    script_execution_timeout_seconds: int = 300

    @model_validator(mode='after')
    def validate_https_in_production(self) -> 'Settings':
        """
        Valida que endpoints HTTP criticos usam HTTPS em producao/staging.
        Endpoints verificados: Prometheus, Alertmanager, OTEL, MLflow, Keycloak.
        Pode ser desabilitado com allow_insecure_http_endpoints=True para staging.
        """
        # Permitir HTTP se flag está habilitada (staging com comunicação interna)
        if self.allow_insecure_http_endpoints:
            return self

        is_prod_staging = self.environment.lower() in ('production', 'staging', 'prod')
        if not is_prod_staging:
            return self

        # Endpoints criticos que devem usar HTTPS em producao
        http_endpoints = []
        if self.prometheus_url.startswith('http://'):
            http_endpoints.append(('prometheus_url', self.prometheus_url))
        if self.alertmanager_url.startswith('http://'):
            http_endpoints.append(('alertmanager_url', self.alertmanager_url))
        if self.otel_exporter_otlp_endpoint.startswith('http://'):
            http_endpoints.append(('otel_exporter_otlp_endpoint', self.otel_exporter_otlp_endpoint))
        if self.mlflow_tracking_uri.startswith('http://'):
            http_endpoints.append(('mlflow_tracking_uri', self.mlflow_tracking_uri))
        if self.keycloak_url.startswith('http://'):
            http_endpoints.append(('keycloak_url', self.keycloak_url))

        if http_endpoints:
            endpoint_list = ', '.join(f'{name}={url}' for name, url in http_endpoints)
            raise ValueError(
                f"Endpoints HTTP inseguros detectados em ambiente {self.environment}: {endpoint_list}. "
                "Use HTTPS em producao/staging para garantir seguranca de dados em transito."
            )

        return self


@lru_cache()
def get_settings() -> Settings:
    """Retorna instância singleton das configurações"""
    return Settings()
