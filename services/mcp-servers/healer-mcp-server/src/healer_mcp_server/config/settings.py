"""Healer MCP Server Configuration"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class HealerMCPServerSettings(BaseSettings):
    """Configurações do Healer MCP Server."""

    service_name: str = "healer-mcp-server"
    service_version: str = "1.0.0"
    log_level: str = "INFO"
    port: int = 3019
    healer_agent_host: str = "self-healing-engine"
    healer_agent_port: int = 8009
    timeout: int = 300

    model_config = SettingsConfigDict(env_prefix="HEALER_MCP_", env_file=".env")


_settings_instance = None


def get_settings() -> HealerMCPServerSettings:
    """Retorna instância singleton de settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = HealerMCPServerSettings()
    return _settings_instance
