"""Settings configuration using Pydantic BaseSettings."""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Service Identity
    SERVICE_NAME: str = "mcp-tool-catalog"
    SERVICE_VERSION: str = "1.0.0"
    HTTP_PORT: int = 8080
    GRPC_PORT: int = 9090
    METRICS_PORT: int = 9091

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="kafka-cluster-kafka-bootstrap:9092",
        description="Kafka bootstrap servers"
    )
    KAFKA_TOOL_SELECTION_REQUEST_TOPIC: str = "mcp.tool.selection.requests"
    KAFKA_TOOL_SELECTION_RESPONSE_TOPIC: str = "mcp.tool.selection.responses"
    KAFKA_CONSUMER_GROUP_ID: str = "mcp-tool-catalog-group"

    # MongoDB Configuration
    MONGODB_URL: str = Field(
        default="mongodb://mongodb-svc:27017",
        description="MongoDB connection URL"
    )
    MONGODB_DATABASE: str = "mcp_tool_catalog"
    MONGODB_TOOLS_COLLECTION: str = "tools"
    MONGODB_SELECTIONS_COLLECTION: str = "selections_history"

    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://redis-cluster:6379",
        description="Redis connection URL"
    )
    CACHE_TTL_SECONDS: int = 3600
    CACHE_ENABLED: bool = True

    # Service Registry Configuration
    SERVICE_REGISTRY_HOST: str = "service-registry"
    SERVICE_REGISTRY_PORT: int = 8080
    HEARTBEAT_INTERVAL_SECONDS: int = 30

    # Genetic Algorithm Configuration
    GA_POPULATION_SIZE: int = 50
    GA_MAX_GENERATIONS: int = 100
    GA_CROSSOVER_PROB: float = 0.7
    GA_MUTATION_PROB: float = 0.2
    GA_TOURNAMENT_SIZE: int = 3
    GA_CONVERGENCE_THRESHOLD: float = 0.01
    GA_TIMEOUT_SECONDS: int = 30

    # Tool Execution Configuration
    TOOL_EXECUTION_TIMEOUT_SECONDS: int = 300
    MAX_CONCURRENT_TOOL_EXECUTIONS: int = 10
    TOOL_RETRY_MAX_ATTEMPTS: int = 3

    # Observability Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    OTEL_EXPORTER_ENDPOINT: Optional[str] = Field(
        default="http://otel-collector:4317",
        description="OpenTelemetry collector endpoint"
    )

    # Analyst Agents Integration (for RAG)
    ANALYST_AGENTS_HOST: str = "analyst-agents"
    ANALYST_AGENTS_PORT: int = 9090


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
