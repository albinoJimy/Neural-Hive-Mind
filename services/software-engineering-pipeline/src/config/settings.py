from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API
    app_name: str = "software-engineering-pipeline"
    app_version: str = "1.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8008
    debug: bool = False
    environment: str = "dev"
    log_level: str = "INFO"
    cors_allowed_origins: list[str] = ["*"]

    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "pipeline_db"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "pipeline-service"

    # OpenTelemetry
    otel_exporter_otlp_endpoint: str | None = None

    # GitHub
    github_token: str = ""
    github_app_id: str | None = None
    github_app_private_key: str | None = None

    # GitLab
    gitlab_token: str = ""
    gitlab_url: str = "https://gitlab.com"

    # Jenkins
    jenkins_url: str = ""
    jenkins_username: str = ""
    # jenkins_password: str = ""  # OBRIGATÓRIO: Definir via External Secrets

    # ArgoCD
    argocd_url: str = ""
    argocd_token: str = ""
    argocd_namespace: str = "argocd"

    # Flux CD
    flux_namespace: str = "flux-system"
    flux_kubeconfig: str = "~/.kube/config"

    # Docker Registry
    docker_registry: str = "ghcr.io"
    docker_registry_username: str = ""
    # docker_registry_password: str = ""  # OBRIGATÓRIO: Definir via External Secrets

    # Intelligence
    anomaly_detection_enabled: bool = True
    anomaly_threshold: float = 0.7
    flaky_test_threshold: int = 3
    pipeline_insights_retention_days: int = 90

    # Orchestration
    default_timeout_minutes: int = 60
    max_retries: int = 3
    rollback_on_health_check_failure: bool = True
    rollback_on_metrics_degradation: bool = True


settings = Settings()
