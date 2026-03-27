"""Modelos de dados para o Architect Agent service."""

from .architecture import (
    ArchitectureType,
    Component,
    Pattern,
    ArchitecturePlan,
)
from .validation import (
    Severity,
    ViolationType,
    Trend,
    Violation,
    Suggestion,
    ValidationReport,
)
from .evolution import (
    DriftType,
    DriftDetection,
    EvolutionHistory,
    ArchitectureDiff,
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
