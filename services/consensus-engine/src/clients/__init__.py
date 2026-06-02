from .mongodb_client import MongoDBClient
from .pheromone_client import PheromoneClient
from .redis_client import RedisClient

# Imports opcionais que dependem de protobuf
try:
    from .analyst_agent_grpc_client import AnalystAgentGrpcClient  # noqa: F401
    from .queen_agent_grpc_client import QueenAgentGrpcClient  # noqa: F401
    from .specialists_grpc_client import SpecialistsGrpcClient  # noqa: F401

    _grcp_available = True
except ImportError as _err:
    import logging

    logging.getLogger(__name__).warning(
        "Optional gRPC clients unavailable: %s: %s",
        type(_err).__name__,
        _err,
    )
    _grcp_available = False

__all__ = [
    "PheromoneClient",
    "MongoDBClient",
    "RedisClient",
]

# Adicionar clients gRPC apenas se disponíveis
if _grcp_available:
    __all__.extend(
        [
            "SpecialistsGrpcClient",
            "QueenAgentGrpcClient",
            "AnalystAgentGrpcClient",
        ]
    )
