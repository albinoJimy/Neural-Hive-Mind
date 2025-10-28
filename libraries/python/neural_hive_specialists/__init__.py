"""
Neural Hive Specialists Library

Biblioteca compartilhada para implementação de especialistas neurais do Neural Hive-Mind.
Fornece classes base, clientes, configuração, schemas de validação e utilitários para
construção de especialistas.

Versão: 1.0.0
Schema Version: 1.0.0
"""

from .base_specialist import BaseSpecialist
from .cached_specialist import CachedSpecialist
from .ensemble_specialist import EnsembleSpecialist
from .ab_testing_specialist import ABTestingSpecialist
from .config import SpecialistConfig
from .mlflow_client import MLflowClient
from .ledger_client import LedgerClient
from .explainability_generator import ExplainabilityGenerator
from .metrics import SpecialistMetrics
from .grpc_server import create_grpc_server_with_observability
from .auth_interceptor import AuthInterceptor
from .schemas import (
    CognitivePlanSchema,
    TaskSchema,
    PlanValidationError,
    PlanVersionIncompatibleError,
    TaskDependencyError,
    SCHEMA_VERSION
)

__version__ = "1.0.0"

__all__ = [
    "BaseSpecialist",
    "CachedSpecialist",
    "EnsembleSpecialist",
    "ABTestingSpecialist",
    "SpecialistConfig",
    "MLflowClient",
    "LedgerClient",
    "ExplainabilityGenerator",
    "SpecialistMetrics",
    "create_grpc_server_with_observability",
    "AuthInterceptor",
    "CognitivePlanSchema",
    "TaskSchema",
    "PlanValidationError",
    "PlanVersionIncompatibleError",
    "TaskDependencyError",
    "SCHEMA_VERSION",
]
