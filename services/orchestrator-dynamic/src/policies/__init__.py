"""
Módulo de políticas OPA para orchestrator-dynamic.

Este módulo fornece integração com Open Policy Agent (OPA) para enforcement
de políticas de governança em tempo de execução.
"""

from .opa_client import OPAClient
from .policy_validator import PolicyValidator, ValidationResult, PolicyViolation, PolicyWarning

__all__ = [
    'OPAClient',
    'PolicyValidator',
    'ValidationResult',
    'PolicyViolation',
    'PolicyWarning',
]
