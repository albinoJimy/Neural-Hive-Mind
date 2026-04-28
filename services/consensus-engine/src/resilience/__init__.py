"""Módulo de resiliência do consensus-engine.

Fornece circuit breakers e políticas de resiliência para chamadas gRPC.
"""

from .circuit_breaker_wrapper import (
    GrpcCircuitBreakerWrapper,
    get_grpc_circuit_breaker,
    init_grpc_circuit_breaker,
)

__all__ = [
    "GrpcCircuitBreakerWrapper",
    "get_grpc_circuit_breaker",
    "init_grpc_circuit_breaker",
]
