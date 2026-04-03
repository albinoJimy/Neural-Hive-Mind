"""Configurações do Code Forge MCP Server."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class CodeForgeSettings(BaseSettings):
    """Configurações do servidor Code Forge MCP."""

    model_config = SettingsConfigDict(
        env_prefix="CODE_FORGE_MCP_", env_file=".env", case_sensitive=False
    )

    # Identidade do serviço
    service_name: str = "code-forge-mcp-server"
    service_version: str = "1.0.0"
    environment: str = "development"
    port: int = 3018

    # MongoDB para armazenamento de artefatos
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "neural_hive_code_forge"

    # Redis para cache
    redis_url: str = "redis://localhost:6379/0"

    # Template Store
    template_store_url: str = "http://localhost:8009"

    # LLM Providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Caching
    cache_ttl_seconds: int = 3600
    enable_cache: bool = True

    # Generation limits
    max_generation_size_mb: int = 10
    timeout_seconds: int = 300


_settings_instance: CodeForgeSettings | None = None


def get_settings() -> CodeForgeSettings:
    """Retorna instância singleton de configurações."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = CodeForgeSettings()
    return _settings_instance
