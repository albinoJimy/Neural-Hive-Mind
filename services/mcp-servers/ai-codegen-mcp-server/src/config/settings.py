"""Configurações do AI CodeGen MCP Server."""

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações do servidor via environment variables."""

    # Informações do serviço
    service_name: str = "ai-codegen-mcp-server"
    service_version: str = "1.0.0"

    # Servidor HTTP
    http_host: str = "0.0.0.0"
    http_port: int = 3000

    # GitHub Copilot
    github_token: str = ""
    github_api_url: str = "https://api.github.com"

    # OpenAI
    openai_api_key: str = ""
    openai_api_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4-turbo-preview"
    openai_code_model: str = "gpt-4-turbo-preview"

    # Provider padrão
    default_provider: Literal["copilot", "openai", "auto"] = "auto"

    # Timeouts
    api_timeout: int = 60
    max_tokens: int = 2048

    # Observability
    otel_endpoint: str = "http://otel-collector:4317"
    log_level: str = "INFO"
    metrics_port: int = 9091

    # CORS
    cors_origins: str = "*"

    class Config:
        env_prefix = ""
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Retorna instância singleton das configurações."""
    return Settings()
