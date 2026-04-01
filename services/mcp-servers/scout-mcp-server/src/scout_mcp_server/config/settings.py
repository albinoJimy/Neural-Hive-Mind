# Scout MCP Server Configuration

from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoutMCPServerSettings(BaseSettings):
    """Configurações do Scout MCP Server."""

    service_name: str = "scout-mcp-server"
    service_version: str = "1.0.0"
    log_level: str = "INFO"

    # Configurações de scanning
    max_files_per_scan: int = 10000
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10MB
    max_search_results: int = 100

    # Diretórios permitidos para scan (segurança)
    allowed_scan_paths: list[str] = ["/workspace", "/app", "."]

    class Config:
        env_prefix = "SCOUT_MCP_"
        env_file = ".env"


_settings_instance: ScoutMCPServerSettings | None = None


def get_settings() -> ScoutMCPServerSettings:
    """Retorna instância singleton de settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = ScoutMCPServerSettings()
    return _settings_instance
