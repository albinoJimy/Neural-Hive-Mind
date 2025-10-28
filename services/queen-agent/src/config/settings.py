from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações do Queen Agent via variáveis de ambiente"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True
    )

    # Service Metadata
    SERVICE_NAME: str = 'queen-agent'
    SERVICE_VERSION: str = '1.0.0'
    ENVIRONMENT: str = 'production'
    LOG_LEVEL: str = 'INFO'

    # FastAPI
    FASTAPI_HOST: str = '0.0.0.0'
    FASTAPI_PORT: int = 8000
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ['*'])

    # gRPC
    GRPC_PORT: int = 50053
    GRPC_MAX_WORKERS: int = 10

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str
    KAFKA_CONSUMER_GROUP: str = 'queen-agent-group'
    KAFKA_TOPICS_CONSENSUS: str = 'plans.consensus'
    KAFKA_TOPICS_TELEMETRY: str = 'telemetry.aggregated'
    KAFKA_TOPICS_INCIDENTS: str = 'incidents.critical'
    KAFKA_TOPICS_STRATEGIC: str = 'strategic.decisions'
    KAFKA_AUTO_OFFSET_RESET: str = 'earliest'

    # MongoDB
    MONGODB_URI: str
    MONGODB_DATABASE: str = 'neural_hive'
    MONGODB_COLLECTION_LEDGER: str = 'strategic_decisions_ledger'
    MONGODB_COLLECTION_EXCEPTIONS: str = 'exception_approvals'

    # Redis
    REDIS_CLUSTER_NODES: str
    REDIS_PASSWORD: str = ''
    REDIS_SSL_ENABLED: bool = True
    REDIS_PHEROMONE_PREFIX: str = 'pheromone:strategic:'
    REDIS_CACHE_TTL_SECONDS: int = 300

    # Neo4j
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    NEO4J_DATABASE: str = 'neo4j'
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = 50

    # Prometheus
    PROMETHEUS_URL: str = 'http://prometheus-server:9090'
    PROMETHEUS_QUERY_TIMEOUT_SECONDS: int = 30

    # Orchestrator Integration
    ORCHESTRATOR_GRPC_HOST: str = 'orchestrator-dynamic'
    ORCHESTRATOR_GRPC_PORT: int = 50051

    # Service Registry Integration
    SERVICE_REGISTRY_GRPC_HOST: str = 'service-registry'
    SERVICE_REGISTRY_GRPC_PORT: int = 50051

    # Decision Engine
    DECISION_CONFIDENCE_THRESHOLD: float = 0.7
    CONFLICT_RESOLUTION_TIMEOUT_SECONDS: int = 60
    REPLANNING_COOLDOWN_SECONDS: int = 300
    MAX_CONCURRENT_DECISIONS: int = 5

    # Observability
    OTEL_EXPORTER_ENDPOINT: str = 'http://jaeger-collector:4317'
    METRICS_PORT: int = 9090


@lru_cache()
def get_settings() -> Settings:
    """Retorna singleton de configurações"""
    return Settings()
