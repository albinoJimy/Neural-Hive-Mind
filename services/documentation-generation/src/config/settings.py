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

    # OpenAI/Anthropic
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    llm_provider: str = "openai"
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.7

    # Neural Hive-Mend Integration
    requirements_engineering_url: str = Field(
        default="http://requirements-engineering:8010",
        validation_alias="REQUIREMENTS_ENGINEERING_URL"
    )

    # Service Info
    service_name: str = "documentation-generation"
    service_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton de Settings."""
    return Settings()
