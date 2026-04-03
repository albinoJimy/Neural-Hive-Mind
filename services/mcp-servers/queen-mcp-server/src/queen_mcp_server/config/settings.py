# Queen MCP Server Configuration

from pydantic_settings import BaseSettings, SettingsConfigDict


class QueenMCPServerSettings(BaseSettings):
    """Configurações do Queen MCP Server."""

    service_name: str = "queen-mcp-server"
    service_version: str = "1.0.0"
    log_level: str = "INFO"

    # Porta do servidor
    port: int = 3012

    # Queen Agent gRPC configuration
    queen_agent_host: str = "queen-agent"
    queen_agent_port: int = 8006

    # Timeout para decisões estratégicas (segundos)
    decision_timeout: int = 30

    # Cache configuration
    cache_ttl_seconds: int = 300

    # Configurações OPA
    opa_url: str = "http://opa:8181"
    opa_policy_path: str = "neuralhive/queen/ethical_guardrails"

    # MongoDB configuration (para ler decisões históricas)
    mongodb_uri: str = "mongodb://mongodb:27017"
    mongodb_database: str = "queen_agent"

    # Neo4j configuration (para contexto estratégico)
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_database: str = "neo4j"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # Redis configuration (para cache e feromônios)
    redis_uri: str = "redis://redis:6379"

    class Config:
        env_prefix = "QUEEN_MCP_"
        env_file = ".env"


_settings_instance: QueenMCPServerSettings | None = None


def get_settings() -> QueenMCPServerSettings:
    """Retorna instância singleton de settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = QueenMCPServerSettings()
    return _settings_instance
