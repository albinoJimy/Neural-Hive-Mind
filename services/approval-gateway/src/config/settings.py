"""Configurações do Approval Gateway service."""

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
        env_prefix="APPROVAL_GW_",
    )

    # API
    api_title: str = "Approval Gateway API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8017

    # MongoDB
    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        validation_alias="MONGODB_URL"
    )
    mongodb_database: str = "nhm_approvals"

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        validation_alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_consumer_group: str = "approval-gateway-group"
    kafka_input_topic: str = "approval.requests"
    kafka_output_topic: str = "approval.responses"

    # LLM
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.3

    # Approval Settings
    auto_approval_threshold: float = 0.8
    auto_rejection_threshold: float = 0.3
    require_human_threshold: float = 0.5

    # Service Info
    service_name: str = "approval-gateway"
    service_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton de Settings."""
    return Settings()
