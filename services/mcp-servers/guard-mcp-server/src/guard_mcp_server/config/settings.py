"""Guard MCP Server Configuration"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class GuardMCPServerSettings(BaseSettings):
    """Configurações do Guard MCP Server."""

    service_name: str = "guard-mcp-server"
    service_version: str = "1.0.0"
    log_level: str = "INFO"
    port: int = 3014
    guard_agent_host: str = "guard-agents"
    guard_agent_port: int = 8008
    trivy_host: str = "trivy"
    trivy_port: int = 8080
    opa_host: str = "opa"
    opa_port: int = 8181
    validation_timeout: int = 300

    model_config = SettingsConfigDict(env_prefix="GUARD_MCP_", env_file=".env")


_settings_instance = None


def get_settings() -> GuardMCPServerSettings:
    """Retorna instância singleton de settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = GuardMCPServerSettings()
    return _settings_instance
