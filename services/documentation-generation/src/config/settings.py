"""Configurações do Documentation Generation service."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centralizadas."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="DOC_GEN_",
    )

    # API
    api_title: str = "Documentation Generation API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8014
    debug: bool = False

    # OpenAI/Anthropic
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    llm_provider: str = "openai"
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4000

    # MongoDB
    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        validation_alias="MONGODB_URL"
    )
    mongodb_database: str = Field(
        default="documentation_generation",
        validation_alias="MONGODB_DATABASE"
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL"
    )

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        validation_alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_topic_docs: str = "documentation-events"

    # Neural Hive-Mind Integration
    requirements_engineering_url: str = Field(
        default="http://requirements-engineering:8010",
        validation_alias="REQUIREMENTS_ENGINEERING_URL"
    )
    architect_agent_url: str = Field(
        default="http://architect-agent:8008",
        validation_alias="ARCHITECT_AGENT_URL"
    )
    knowledge_graph_url: str = Field(
        default="http://knowledge-graph-rag:8016",
        validation_alias="KNOWLEDGE_GRAPH_URL"
    )

    # Documentation Storage
    docs_storage_path: str = Field(
        default="/docs",
        validation_alias="DOCS_STORAGE_PATH"
    )

    # Service Info
    service_name: str = "documentation-generation"
    service_version: str = "0.1.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton de Settings."""
    return Settings()
