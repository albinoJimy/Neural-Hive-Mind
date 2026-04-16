"""Configurações do Data Migration Service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centralizadas."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="DATA_MIGRATION_",
    )

    # API
    api_title: str = "Data Migration API"
    api_version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8019
    debug: bool = False

    # OpenAI/Anthropic
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    llm_provider: str = "openai"
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 8000

    # PostgreSQL (Legacy Database)
    postgres_url: str = Field(
        default="postgresql://localhost:5432/legacy", validation_alias="POSTGRES_URL"
    )
    postgres_database: str = Field(default="legacy", validation_alias="POSTGRES_DATABASE")

    # MongoDB (Metadata)
    mongodb_url: str = Field(default="mongodb://localhost:27017", validation_alias="MONGODB_URL")
    mongodb_database: str = Field(default="data_migration", validation_alias="MONGODB_DATABASE")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/1", validation_alias="REDIS_URL")

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092", validation_alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_consumer_group: str = "data-migration-consumers"
    kafka_output_topic: str = "migration.progress"

    # S3/MinIO (Data dumps)
    s3_endpoint: str = Field(default="http://localhost:9000", validation_alias="S3_ENDPOINT")
    s3_access_key: str = Field(default="", validation_alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", validation_alias="S3_SECRET_KEY")
    s3_bucket: str = Field(default="nhm-migration-dumps", validation_alias="S3_BUCKET")
    s3_use_ssl: bool = False

    # Debezium CDC
    debezium_url: str = Field(default="http://localhost:8083", validation_alias="DEBEZIUM_URL")

    # Service Registry gRPC
    service_registry_grpc_host: str = Field(
        default="service-registry", validation_alias="SERVICE_REGISTRY_GRPC_HOST"
    )
    service_registry_grpc_port: int = Field(
        default=50051, validation_alias="SERVICE_REGISTRY_GRPC_PORT"
    )
    service_registry_namespace: str = Field(
        default="default", validation_alias="SERVICE_REGISTRY_NAMESPACE"
    )
    service_registry_cluster: str = Field(
        default="neural-hive", validation_alias="SERVICE_REGISTRY_CLUSTER"
    )

    # Neural Hive-Mind Integration
    gateway_url: str = Field(
        default="http://gateway-intencoes:8000", validation_alias="GATEWAY_URL"
    )
    orchestrator_url: str = Field(
        default="http://orchestrator-dynamic:8003", validation_alias="ORCHESTRATOR_URL"
    )
    service_registry_url: str = Field(
        default="http://service-registry:8007", validation_alias="SERVICE_REGISTRY_URL"
    )

    # Migration Settings
    batch_size: int = 1000
    max_parallel_migrations: int = 5
    rollback_timeout_seconds: int = 30

    # Service Info
    service_name: str = "data-migration"
    service_version: str = "1.0.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton de Settings."""
    return Settings()
