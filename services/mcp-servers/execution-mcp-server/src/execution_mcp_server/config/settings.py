# Execution MCP Server Configuration

from pydantic_settings import BaseSettings


class ExecutionMCPServerSettings(BaseSettings):
    """Configurações do Execution MCP Server."""

    service_name: str = "execution-mcp-server"
    service_version: str = "1.0.0"
    log_level: str = "INFO"

    # Porta do servidor (spec: INFRA-001-06)
    port: int = 3014

    # Execution Ticket Service configuration
    execution_ticket_host: str = "execution-ticket-service"
    execution_ticket_port: int = 8008

    # Timeout para operações de ticket (segundos)
    ticket_timeout: int = 30

    # JWT configuration
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    default_token_ttl: int = 3600

    # Webhook configuration
    webhook_timeout: int = 10
    webhook_max_retries: int = 3

    # MongoDB configuration
    mongodb_uri: str = "mongodb://mongodb:27017"
    mongodb_database: str = "execution_tickets"

    # Redis configuration (para cache)
    redis_uri: str = "redis://redis:6379"

    class Config:
        env_prefix = "EXECUTION_MCP_"
        env_file = ".env"


_settings_instance: ExecutionMCPServerSettings | None = None


def get_settings() -> ExecutionMCPServerSettings:
    """Retorna instância singleton de settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = ExecutionMCPServerSettings()
    return _settings_instance
