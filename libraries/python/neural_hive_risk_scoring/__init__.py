"""
Neural Hive Risk Scoring Library

Biblioteca reutilizável para avaliação de risco multi-domínio.
Suporta domínios: Business, Technical, Security, Operational, Compliance.
"""

from .config import RiskDomain, RiskBand, RiskScoringConfig
from .models import RiskFactor, RiskAssessment, RiskMatrix
from .engine import RiskScoringEngine

__version__ = "1.0.0"

__all__ = [
    "RiskScoringEngine",
    "RiskDomain",
    "RiskBand",
    "RiskFactor",
    "RiskAssessment",
    "RiskMatrix",
    "RiskScoringConfig",
]
