"""
Neural Hive-Mind Exceptions Library

Biblioteca de exceções centralizada para consistent error handling
em todos os serviços da plataforma Neural Hive-Mind.

Uso:
    from neural_hive_exceptions import (
        NeuralHiveError,
        ValidationError,
        ConfigurationError,
        ConnectionError,
        TimeoutError,
        DatabaseError,
        KafkaError,
        GRPCError,
        grpc_error_to_status
    )
"""

from .base import ErrorContext, NeuralHiveError, error_code
from .configuration import ConfigErrorCode, ConfigurationError
from .grpc import GRPCError, HTTPStatusFromGRPC, grpc_error_to_status
from .infrastructure import (
    ConnectionError,
    DatabaseError,
    InfrastructureErrorCode,
    KafkaError,
    TimeoutError,
)
from .validation import SchemaValidationError, ValidationError, ValidationErrorCode

__all__ = [
    # Base
    "NeuralHiveError",
    "error_code",
    "ErrorContext",
    # Validation
    "ValidationError",
    "ValidationErrorCode",
    "SchemaValidationError",
    # Configuration
    "ConfigurationError",
    "ConfigErrorCode",
    # Infrastructure
    "ConnectionError",
    "TimeoutError",
    "DatabaseError",
    "KafkaError",
    "InfrastructureErrorCode",
    # gRPC
    "GRPCError",
    "grpc_error_to_status",
    "HTTPStatusFromGRPC",
]

__version__ = "1.1.0"
