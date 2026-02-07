"""
Neural Hive Specialists Library

Biblioteca compartilhada para implementação de especialistas neurais do Neural Hive-Mind.
Fornece classes base, clientes, configuração, schemas de validação e utilitários para
construção de especialistas.

Versão: 1.0.9
Schema Version: 1.0.0
"""

# IMPORTANT: Apply sklearn compatibility patch BEFORE any imports
# This fixes cross-version sklearn compatibility issues (1.3.x -> 1.5.x)
# particularly the monotonic_cst attribute error.
try:
    from .sklearn_compat import apply_sklearn_compatibility_patch
    apply_sklearn_compatibility_patch()
except Exception:
    pass  # Patch failures should not prevent module loading

# Registrar módulo probabilistic_wrapper no sys.modules para compatibilidade
# com modelos MLflow que foram treinados com import direto do módulo.
# O pickle deserializa buscando 'probabilistic_wrapper' no sys.modules.
import sys
from . import probabilistic_wrapper as _pw_module

sys.modules["probabilistic_wrapper"] = _pw_module

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
from .probabilistic_wrapper import ProbabilisticModelWrapper
from .schemas import (
    CognitivePlanSchema,
    TaskSchema,
    PlanValidationError,
    PlanVersionIncompatibleError,
    TaskDependencyError,
    SCHEMA_VERSION,
)

__version__ = "1.0.10"

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
    "ProbabilisticModelWrapper",
]
