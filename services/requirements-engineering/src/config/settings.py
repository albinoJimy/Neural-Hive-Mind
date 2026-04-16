"""Configurações do Requirements Engineering Service."""

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
        env_prefix="REQ_ENG_",
    )

    # API
    api_title: str = "Requirements Engineering API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8010
    debug: bool = False

    # OpenAI/Anthropic
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    llm_provider: str = "openai"  # openai or anthropic
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4000

    # MongoDB
    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        validation_alias="MONGODB_URL"
    )
    mongodb_database: str = Field(
        default="requirements_engineering",
        validation_alias="MONGODB_DATABASE"
    )
    collection_requirements: str = "requirements"
    collection_user_stories: str = "user_stories"
    collection_acceptance_criteria: str = "acceptance_criteria"

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
    kafka_topic_requirements: str = "requirements-events"
    kafka_consumer_group: str = "requirements-engineering-group"

    # Neural Hive-Mend Integration
    gateway_url: str = Field(
        default="http://gateway-intencoes:8000",
        validation_alias="GATEWAY_URL"
    )
    orchestrator_url: str = Field(
        default="http://orchestrator-dynamic:8003",
        validation_alias="ORCHESTRATOR_URL"
    )

    # Service Info
    service_name: str = "requirements-engineering"
    service_version: str = "0.1.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton de Settings."""
    return Settings()
