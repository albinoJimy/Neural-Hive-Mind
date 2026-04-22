"""Configurações do Test Generation service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centralizadas."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="TEST_GEN_",
    )

    # API
    api_title: str = "Test Generation API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8013

    # MongoDB
    mongodb_url: str = Field(default="mongodb://localhost:27017", validation_alias="MONGODB_URL")
    mongodb_database: str = "nhm_tests"

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092", validation_alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_consumer_group: str = "test-generation-group"
    kafka_input_topic: str = "requirements.generated"
    kafka_output_topic: str = "tests.generated"

    # LLM
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.3

    # Knowledge Graph
    knowledge_graph_url: str = Field(
        default="http://knowledge-graph-rag:8016", validation_alias="KNOWLEDGE_GRAPH_URL"
    )

    # Test Generation Settings
    default_test_framework: str = Field(default="pytest", description="Framework de testes padrão")
    coverage_target: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Cobertura de código alvo"
    )
    max_test_cases_per_requirement: int = Field(
        default=5, ge=1, le=20, description="Máximo de casos de teste por requisito"
    )

    # Service Info
    service_name: str = "test-generation"
    service_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton de Settings."""
    return Settings()
