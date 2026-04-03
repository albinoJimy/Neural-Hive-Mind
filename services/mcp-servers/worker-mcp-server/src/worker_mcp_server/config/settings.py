"""Worker MCP Server Configuration"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerMCPServerSettings(BaseSettings):
    """Configurações do Worker MCP Server."""

    service_name: str = "worker-mcp-server"
    service_version: str = "1.0.0"
    log_level: str = "INFO"
    port: int = 3013
    worker_agent_host: str = "worker-agents"
    worker_agent_port: int = 8005
    orchestrator_host: str = "orchestrator-dynamic"
    orchestrator_port: int = 8003
    service_registry_host: str = "service-registry"
    service_registry_port: int = 8007
    execution_timeout: int = 300

    model_config = SettingsConfigDict(env_prefix="WORKER_MCP_", env_file=".env")


_settings_instance = None


def get_settings() -> WorkerMCPServerSettings:
    """Retorna instância singleton de settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = WorkerMCPServerSettings()
    return _settings_instance
