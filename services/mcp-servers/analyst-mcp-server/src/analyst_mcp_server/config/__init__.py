"""Configurações do Analyst MCP Server."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AnalystSettings(BaseSettings):
    """Configurações do servidor Analyst MCP."""

    model_config = SettingsConfigDict(
        env_prefix="ANALYST_MCP_", env_file=".env", case_sensitive=False
    )

    # Identidade do serviço
    service_name: str = "analyst-mcp-server"
    service_version: str = "1.0.0"
    environment: str = "development"
    port: int = 3016  # spec: INFRA-001-05

    # MongoDB para armazenamento de insights
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "neural_hive_analyst"

    # Redis para cache de métricas
    redis_url: str = "redis://localhost:6379/0"

    # Feature Store para dados de time-series
    feature_store_url: str = "http://localhost:8006"

    # Timeouts
    query_timeout_ms: int = 30000
    analysis_timeout_ms: int = 60000

    # Paginação
    default_page_size: int = 50
    max_page_size: int = 1000


_settings_instance: AnalystSettings | None = None


def get_settings() -> AnalystSettings:
    """Retorna instância singleton de configurações."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = AnalystSettings()
    return _settings_instance
