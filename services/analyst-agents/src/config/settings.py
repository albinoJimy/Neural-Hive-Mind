from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from neural_hive_api.kafka import KafkaTopicsConfig
from neural_hive_security.cors import CORSConfig


class AnalystTopics(KafkaTopicsConfig):
    """Configuração de tópicos Kafka para analyst-agents."""

    PREFIX = "analyst"

    def __init__(self):
        super().__init__()
        self.TELEMETRY = self.get_topic("telemetry", "aggregated")
        self.CONSENSUS = self.get_topic("plans", "consensus")
        self.EXECUTION = self.get_topic("execution", "results")
        self.PHEROMONES = self.get_topic("pheromones", "signals")
        self.INSIGHTS = self.get_topic("insights", "analyzed")

    def get_all_topics(self) -> dict[str, str]:
        """Retorna mapping nome_tópico → tópico."""
        return {
            "telemetry": self.TELEMETRY,
            "consensus": self.CONSENSUS,
            "execution": self.EXECUTION,
            "pheromones": self.PHEROMONES,
            "insights": self.INSIGHTS,
        }


class Settings(BaseSettings):
    # Service
    SERVICE_NAME: str = "analyst-agents"
    SERVICE_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # FastAPI
    FASTAPI_HOST: str = "0.0.0.0"
    FASTAPI_PORT: int = 8000

    # CORS - Serviço interno (gRPC/Kafka), sem CORS
    IS_PUBLIC_API: bool = Field(default=False)

    @property
    def CORS_ORIGINS(self) -> list[str]:
        """CORS origins dinâmicas por ambiente."""
        return CORSConfig.get_origins_for_environment(
            self.ENVIRONMENT, is_public_api=self.IS_PUBLIC_API
        )

    # gRPC
    GRPC_ENABLED: bool = True
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50051
    GRPC_MAX_WORKERS: int = 10

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str
    KAFKA_CONSUMER_GROUP: str = "analyst-agents-group"
    KAFKA_AUTO_OFFSET_RESET: str = "earliest"
    KAFKA_ENABLE_AUTO_COMMIT: bool = False

    # Kafka Topics (gerenciado via AnalystTopics)
    topics: AnalystTopics = AnalystTopics()

    # MongoDB
    MONGODB_URI: str
    MONGODB_DATABASE: str = "neural_hive"
    MONGODB_COLLECTION_INSIGHTS: str = "analyst_insights"
    MONGODB_MAX_POOL_SIZE: int = 100
    MONGODB_MIN_POOL_SIZE: int = 10

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB: int = 0
    REDIS_INSIGHTS_TTL: int = 3600

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str | None = None
    NEO4J_DATABASE: str = "neo4j"

    # ClickHouse
    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 9000
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str | None = None
    CLICKHOUSE_DATABASE: str = "neural_hive"

    # PostgreSQL
    POSTGRESQL_HOST: str = "localhost"
    POSTGRESQL_PORT: int = 5432
    POSTGRESQL_USER: str = "postgres"
    POSTGRESQL_PASSWORD: str | None = None
    POSTGRESQL_DATABASE: str = "neural_hive"
    POSTGRESQL_MIN_POOL_SIZE: int = 10
    POSTGRESQL_MAX_POOL_SIZE: int = 100

    # Elasticsearch
    ELASTICSEARCH_HOSTS: list[str] = Field(default=["http://localhost:9200"])
    ELASTICSEARCH_USER: str | None = None
    ELASTICSEARCH_PASSWORD: str | None = None

    # Prometheus
    PROMETHEUS_URL: str = "http://localhost:9090"

    # Memory Layer API
    MEMORY_LAYER_API_URL: str = "http://memory-layer-api:8000"

    # Queen Agent gRPC
    QUEEN_AGENT_GRPC_HOST: str = "queen-agent"
    QUEEN_AGENT_GRPC_PORT: int = 50051

    # SPIFFE/SPIRE mTLS
    SPIFFE_ENABLED: bool = False
    SPIFFE_SOCKET_PATH: str = "unix:///run/spire/sockets/agent.sock"
    SPIFFE_TRUST_DOMAIN: str = "neural-hive.local"
    SPIFFE_ENABLE_X509: bool = False

    # Service Registry
    SERVICE_REGISTRY_GRPC_HOST: str = "service-registry"
    SERVICE_REGISTRY_GRPC_PORT: int = 50051

    # OpenTelemetry
    OTEL_EXPORTER_OTLP_ENDPOINT: str = (
        "https://opentelemetry-collector.observability.svc.cluster.local:4317"
    )
    OTEL_SERVICE_NAME: str = "analyst-agents"

    # Analytics
    ANALYTICS_BATCH_SIZE: int = 1000
    ANALYTICS_WINDOW_SIZE_SECONDS: int = 300
    ANALYTICS_MIN_CONFIDENCE: float = 0.7
    ANALYTICS_ENABLE_SPARK: bool = False

    # Embeddings
    EMBEDDINGS_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDINGS_DIMENSION: int = 384

    @model_validator(mode="after")
    def validate_cors_in_production(self) -> "Settings":
        """
        Valida que serviços internos não usam wildcard CORS em produção.
        """
        is_prod = self.ENVIRONMENT.lower() in ("production", "prod")

        if not is_prod:
            return self

        # Serviços internos NÃO podem usar wildcard
        if not self.IS_PUBLIC_API and "*" in self.CORS_ORIGINS:
            raise ValueError(
                "Internal services cannot use wildcard CORS in production. "
                f"Service: {self.SERVICE_NAME}, Environment: {self.ENVIRONMENT}"
            )

        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
