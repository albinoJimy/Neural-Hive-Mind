"""
Chaos Engineering Module para Self-Healing Engine.

Este módulo implementa uma suite de Chaos Engineering nativa em Python
integrada ao Self-Healing Engine para validação de playbooks de remediação.

Componentes principais:
- ChaosEngine: Orquestrador principal de experimentos
- FaultInjectors: Injetores de falhas (network, pod, resource, application)
- Validators: Validadores de playbooks e health checks
- ScenarioLibrary: Biblioteca de cenários pré-definidos
"""

from .chaos_engine import ChaosEngine
from .chaos_models import (
    ChaosExperiment,
    ChaosExperimentStatus,
    FaultInjection,
    FaultType,
    ValidationResult,
    ExperimentReport,
)

__all__ = [
    "ChaosEngine",
    "ChaosExperiment",
    "ChaosExperimentStatus",
    "FaultInjection",
    "FaultType",
    "ValidationResult",
    "ExperimentReport",
]
