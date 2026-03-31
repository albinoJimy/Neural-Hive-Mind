"""
Neural Hive-Mind Exceptions Library

Biblioteca de exceções centralizada para consistent error handling
em todos os serviços da plataforma Neural Hive-Mind.

Uso:
    from neural_hive_exceptions import (
        NeuralHiveError,
        ValidationError,
        ConfigurationError,
        GRPCError,
        grpc_error_to_status
    )
"""

from .base import NeuralHiveError, error_code
from .validation import ValidationError, ValidationErrorCode
from .configuration import ConfigurationError, ConfigErrorCode
from .grpc import GRPCError, grpc_error_to_status

__all__ = [
    "NeuralHiveError",
    "ValidationError",
    "ValidationErrorCode",
    "ConfigurationError",
    "ConfigErrorCode",
    "GRPCError",
    "error_code",
    "grpc_error_to_status",
]

__version__ = "1.0.0"
