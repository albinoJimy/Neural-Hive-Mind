"""
Neural Hive Risk Scoring Library

Biblioteca reutilizável para avaliação de risco multi-domínio.
Suporta domínios: Business, Technical, Security, Operational, Compliance.
"""

from .config import RiskBand, RiskScoringConfig
from .models import RiskFactor, RiskAssessment, RiskMatrix
from .engine import RiskScoringEngine
from neural_hive_domain import UnifiedDomain

__version__ = "1.0.0"

__all__ = [
    "RiskScoringEngine",
    "UnifiedDomain",
    "RiskBand",
    "RiskFactor",
    "RiskAssessment",
    "RiskMatrix",
    "RiskScoringConfig",
]
