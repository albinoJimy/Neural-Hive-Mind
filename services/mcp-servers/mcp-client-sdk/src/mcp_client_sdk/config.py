# MCP Client SDK Configuration

import os
from dataclasses import dataclass


@dataclass
class MCPClientConfig:
    """Configurações do MCP Client."""

    default_timeout: int = 30
    max_retries: int = 3
    connection_pool_size: int = 10

    class Config:
        env_prefix = "MCP_CLIENT_"


_config_instance: MCPClientConfig | None = None


def get_config() -> MCPClientConfig:
    """Retorna instância singleton de configuração."""
    global _config_instance
    if _config_instance is None:
        timeout = int(os.getenv("MCP_CLIENT_TIMEOUT", "30"))
        retries = int(os.getenv("MCP_CLIENT_MAX_RETRIES", "3"))
        pool_size = int(os.getenv("MCP_CLIENT_POOL_SIZE", "10"))

        _config_instance = MCPClientConfig(
            default_timeout=timeout, max_retries=retries, connection_pool_size=pool_size
        )
    return _config_instance
