from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    # Service
    SERVICE_NAME: str = 'analyst-agents'
    SERVICE_VERSION: str = '1.0.0'
    ENVIRONMENT: str = 'development'
    LOG_LEVEL: str = 'INFO'

    # FastAPI
    FASTAPI_HOST: str = '0.0.0.0'
    FASTAPI_PORT: int = 8000
    CORS_ORIGINS: List[str] = Field(default=['*'])

    # gRPC
    GRPC_ENABLED: bool = True
    GRPC_HOST: str = '0.0.0.0'
    GRPC_PORT: int = 50051
    GRPC_MAX_WORKERS: int = 10

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str
    KAFKA_CONSUMER_GROUP: str = 'analyst-agents-group'
    KAFKA_TOPICS_TELEMETRY: str = 'telemetry.aggregated'
    KAFKA_TOPICS_CONSENSUS: str = 'plans.consensus'
    KAFKA_TOPICS_EXECUTION: str = 'execution.results'
    KAFKA_TOPICS_PHEROMONES: str = 'pheromones.signals'
    KAFKA_TOPICS_INSIGHTS: str = 'insights.analyzed'
    KAFKA_AUTO_OFFSET_RESET: str = 'earliest'
    KAFKA_ENABLE_AUTO_COMMIT: bool = False

    # MongoDB
    MONGODB_URI: str
    MONGODB_DATABASE: str = 'neural_hive'
    MONGODB_COLLECTION_INSIGHTS: str = 'analyst_insights'
    MONGODB_MAX_POOL_SIZE: int = 100
    MONGODB_MIN_POOL_SIZE: int = 10

    # Redis
    REDIS_HOST: str = 'localhost'
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    REDIS_INSIGHTS_TTL: int = 3600

    # Neo4j
    NEO4J_URI: str = 'bolt://localhost:7687'
    NEO4J_USER: str = 'neo4j'
    NEO4J_PASSWORD: Optional[str] = None
    NEO4J_DATABASE: str = 'neo4j'

    # ClickHouse
    CLICKHOUSE_HOST: str = 'localhost'
    CLICKHOUSE_PORT: int = 9000
    CLICKHOUSE_USER: str = 'default'
    CLICKHOUSE_PASSWORD: Optional[str] = None
    CLICKHOUSE_DATABASE: str = 'neural_hive'

    # Elasticsearch
    ELASTICSEARCH_HOSTS: List[str] = Field(default=['http://localhost:9200'])
    ELASTICSEARCH_USER: Optional[str] = None
    ELASTICSEARCH_PASSWORD: Optional[str] = None

    # Prometheus
    PROMETHEUS_URL: str = 'http://localhost:9090'

    # Memory Layer API
    MEMORY_LAYER_API_URL: str = 'http://memory-layer-api:8000'

    # Queen Agent gRPC
    QUEEN_AGENT_GRPC_HOST: str = 'queen-agent'
    QUEEN_AGENT_GRPC_PORT: int = 50051

    # Service Registry
    SERVICE_REGISTRY_GRPC_HOST: str = 'service-registry'
    SERVICE_REGISTRY_GRPC_PORT: int = 50051

    # OpenTelemetry
    OTEL_EXPORTER_OTLP_ENDPOINT: str = 'http://localhost:4317'
    OTEL_SERVICE_NAME: str = 'analyst-agents'

    # Analytics
    ANALYTICS_BATCH_SIZE: int = 1000
    ANALYTICS_WINDOW_SIZE_SECONDS: int = 300
    ANALYTICS_MIN_CONFIDENCE: float = 0.7
    ANALYTICS_ENABLE_SPARK: bool = False

    # Embeddings
    EMBEDDINGS_MODEL: str = 'sentence-transformers/all-MiniLM-L6-v2'
    EMBEDDINGS_DIMENSION: int = 384

    class Config:
        env_file = '.env'
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
