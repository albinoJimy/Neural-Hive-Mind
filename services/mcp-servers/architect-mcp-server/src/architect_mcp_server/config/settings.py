"""Architect MCP Server Configuration"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ArchitectMCPServerSettings(BaseSettings):
    """Configurações do Architect MCP Server."""

    service_name: str = "architect-mcp-server"
    service_version: str = "1.0.0"
    log_level: str = "INFO"
    port: int = 3017
    architect_agent_host: str = "architect-agent"
    architect_agent_port: int = 8009
    validation_timeout: int = 300
    analysis_timeout: int = 600
    doc_generation_timeout: int = 120

    model_config = SettingsConfigDict(env_prefix="ARCHITECT_MCP_", env_file=".env")


_settings_instance = None


def get_settings() -> ArchitectMCPServerSettings:
    """Retorna instância singleton de settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = ArchitectMCPServerSettings()
    return _settings_instance
