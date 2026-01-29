"""Client modules for external integrations.

ServiceRegistryClient é importado sob demanda (lazy) pois depende de
neural_hive_integration que não está sempre disponível (ex: em testes unitários).
"""
from .mongodb_client import MongoDBClient
from .redis_client import RedisClient
from .kafka_request_consumer import KafkaRequestConsumer
from .kafka_response_producer import KafkaResponseProducer
from .mcp_server_client import MCPServerClient
from .mcp_exceptions import (
    MCPError,
    MCPServerError,
    MCPTransportError,
    MCPProtocolError,
    MCPToolNotFoundError,
    MCPInvalidParamsError,
)

# Lazy import para ServiceRegistryClient (depende de neural_hive_integration)
_ServiceRegistryClient = None


def __getattr__(name: str):
    """Lazy loading de módulos com dependências externas pesadas."""
    global _ServiceRegistryClient
    if name == "ServiceRegistryClient":
        if _ServiceRegistryClient is None:
            from .service_registry_client import ServiceRegistryClient as _SRC
            _ServiceRegistryClient = _SRC
        return _ServiceRegistryClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MongoDBClient",
    "RedisClient",
    "KafkaRequestConsumer",
    "KafkaResponseProducer",
    "ServiceRegistryClient",
    "MCPServerClient",
    "MCPError",
    "MCPServerError",
    "MCPTransportError",
    "MCPProtocolError",
    "MCPToolNotFoundError",
    "MCPInvalidParamsError",
]
