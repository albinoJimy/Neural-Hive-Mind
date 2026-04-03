"""
neural_hive_opa - Biblioteca padronizada para integração OPA.

Cliente Open Policy Agent com cache, circuit breaker e métricas.
"""
from neural_hive_opa.cache import OPACache
from neural_hive_opa.client import OPAClient
from neural_hive_opa.config import OPAConfig
from neural_hive_opa.exceptions import (
    OPAConnectionError,
    OPAEvaluationError,
    OPAPolicyNotFoundError,
)
from neural_hive_opa.metrics import OPAMetrics
from neural_hive_opa.models import PolicyRequest, PolicyResponse, Violation, ViolationSeverity

__all__ = [
    # Client
    "OPAClient",
    # Config
    "OPAConfig",
    # Cache
    "OPACache",
    # Models
    "PolicyRequest",
    "PolicyResponse",
    "Violation",
    "ViolationSeverity",
    # Exceptions
    "OPAConnectionError",
    "OPAEvaluationError",
    "OPAPolicyNotFoundError",
    # Metrics
    "OPAMetrics",
]

__version__ = "0.1.0"
