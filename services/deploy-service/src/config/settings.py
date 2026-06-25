"""
Deploy Service Configuration.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Deploy Service settings."""

    # API
    api_title: str = "Deploy Service API"
    api_version: str = "1.0.0"
    api_prefix: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8010
    workers: int = 1

    # Kubernetes
    kubeconfig_path: str = "/root/.kube/config"
    cluster_name: str = "nhm-cluster"
    default_namespace: str = "default"

    # Pull secret para imagens privadas (GHCR). Replicado para o namespace alvo
    # e referenciado em imagePullSecrets do pod gerado.
    image_pull_secret: str = "ghcr-secret"
    image_pull_secret_source_namespace: str = "neural-hive"

    # Deployment defaults
    default_replicas: int = 2
    default_cpu: str = "500m"
    default_memory: str = "512Mi"
    default_cpu_limit: str = "1000m"
    default_memory_limit: str = "1Gi"

    # Health check defaults
    liveness_path: str = "/health/live"
    readiness_path: str = "/health/ready"
    health_check_delay: int = 10
    health_check_period: int = 10

    # Rollback
    rollback_enabled: bool = True
    rollback_history_limit: int = 10

    # Observability
    enable_tracing: bool = True
    otel_endpoint: str = "http://jaeger:4317"
    log_level: str = "INFO"

    # MongoDB (para armazenar estado dos deployments)
    mongodb_url: str = "mongodb://mongodb:27017"
    mongodb_database: str = "deploy_service"

    # Kafka (para eventos de deploy)
    kafka_bootstrap_servers: str = "kafka:9092"
    deploy_events_topic: str = "deployment-events"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
