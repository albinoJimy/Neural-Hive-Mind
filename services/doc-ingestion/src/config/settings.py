"""Configurações do Doc Ingestion Service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centralizadas."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="DOC_INGEST_",
    )

    # API
    api_title: str = "Doc Ingestion API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8018
    debug: bool = False

    # OpenAI/Anthropic
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    llm_provider: str = "openai"  # openai or anthropic
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4000

    # MongoDB
    mongodb_url: str = Field(default="mongodb://localhost:27017", validation_alias="MONGODB_URL")
    mongodb_database: str = Field(default="doc_ingestion", validation_alias="MONGODB_DATABASE")
    collection_documents: str = "documents"
    collection_entities: str = "entities"
    collection_parsing_jobs: str = "parsing_jobs"

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092", validation_alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_consumer_group: str = "doc-ingestion-consumers"
    kafka_input_topic: str = "documents.uploaded"
    kafka_output_topic: str = "entities.extracted"
    kafka_dlq_topic: str = "doc-ingestion.dlq"

    # S3/MinIO Storage
    s3_endpoint: str = Field(default="http://localhost:9000", validation_alias="S3_ENDPOINT")
    s3_access_key: str = Field(default="", validation_alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", validation_alias="S3_SECRET_KEY")
    s3_bucket: str = Field(default="doc-ingestion", validation_alias="S3_BUCKET")
    s3_secure: bool = False

    # Service Registry
    service_registry_grpc_host: str = Field(
        default="service-registry", validation_alias="SERVICE_REGISTRY_GRPC_HOST"
    )
    service_registry_grpc_port: int = Field(
        default=50051, validation_alias="SERVICE_REGISTRY_GRPC_PORT"
    )

    # Processing Settings
    max_file_size_mb: int = 50
    allowed_extensions: list[str] = Field(default=[".pdf", ".docx", ".xlsx", ".vsdx", ".json"])
    chunk_size_tokens: int = 2000
    chunk_overlap_tokens: int = 200

    # Entity Extraction Settings
    entity_types: list[str] = Field(
        default=["services", "apis", "data_models", "workflows", "components"]
    )
    extraction_confidence_threshold: float = 0.7

    # Neural Hive-Mind Integration
    gateway_url: str = Field(
        default="http://gateway-intencoes:8000", validation_alias="GATEWAY_URL"
    )
    orchestrator_url: str = Field(
        default="http://orchestrator-dynamic:8003", validation_alias="ORCHESTRATOR_URL"
    )

    # Service Info
    service_name: str = "doc-ingestion"
    service_version: str = "0.1.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton de Settings."""
    return Settings()
