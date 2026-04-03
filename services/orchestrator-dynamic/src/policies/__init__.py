"""
Módulo de políticas OPA para orchestrator-dynamic.

Este módulo fornece integração com Open Policy Agent (OPA) para enforcement
de políticas de governança em tempo de execução.

Migração para biblioteca unificada neural_hive_opa (INFRA-002).
"""

# Importar wrapper de compatibilidade que usa neural_hive_opa
from .opa_client import OPAClient

# Importar classes locais
from .policy_validator import PolicyValidator, PolicyViolation, PolicyWarning, ValidationResult

__all__ = [
    "OPAClient",
    "PolicyValidator",
    "PolicyViolation",
    "PolicyWarning",
    "ValidationResult",
]
