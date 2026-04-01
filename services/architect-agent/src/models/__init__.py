"""Modelos de dados para o Architect Agent service."""

from .architecture import (
    ArchitecturePlan,
    ArchitectureType,
    Component,
    Pattern,
)
from .evolution import (
    ArchitectureDiff,
    DriftDetection,
    DriftType,
    EvolutionHistory,
)
from .validation import (
    Severity,
    Suggestion,
    Trend,
    ValidationReport,
    Violation,
    ViolationType,
)

__all__ = [
    # Architecture
    "ArchitectureType",
    "Component",
    "Pattern",
    "ArchitecturePlan",
    # Validation
    "Severity",
    "ViolationType",
    "Trend",
    "Violation",
    "Suggestion",
    "ValidationReport",
    # Evolution
    "DriftType",
    "DriftDetection",
    "EvolutionHistory",
    "ArchitectureDiff",
]
