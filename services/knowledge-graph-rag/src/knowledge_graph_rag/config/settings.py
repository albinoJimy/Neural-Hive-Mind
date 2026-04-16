"""Configurações do Knowledge Graph RAG service."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centralizadas."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="KG_RAG_",
    )

    # API
    api_title: str = "Knowledge Graph RAG API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8016

    # Neo4j
    neo4j_uri: str = Field(
        default="bolt://localhost:7687",
        validation_alias="NEO4J_URI"
    )
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    neo4j_password: str = Field(default="password", validation_alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", validation_alias="NEO4J_DATABASE")

    # Qdrant Vector DB
    qdrant_url: str = Field(
        default="http://localhost:6333",
        validation_alias="QDRANT_URL"
    )
    qdrant_host: str = Field(default="localhost", validation_alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, validation_alias="QDRANT_PORT")
    qdrant_collection: str = "nhm_knowledge"
    qdrant_collection_templates: str = "nhm_templates"
    qdrant_collection_code: str = "nhm_code"

    # OpenAI Embeddings
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.7

    # Service Info
    service_name: str = "knowledge-graph-rag"
    service_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton de Settings."""
    return Settings()
