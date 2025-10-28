"""
Configuração específica do Technical Specialist.
"""

from typing import List
import sys
import os

# Adicionar biblioteca ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..', 'libraries/python'))

from neural_hive_specialists import SpecialistConfig


class TechnicalSpecialistConfig(SpecialistConfig):
    """Configuração do Technical Specialist."""

    # Override defaults
    specialist_type: str = "technical"
    service_name: str = "specialist-technical"
    mlflow_experiment_name: str = "technical-specialist"
    mlflow_model_name: str = "technical-evaluator"

    # Domínios suportados
    supported_domains: List[str] = [
        "security-analysis",
        "architecture-review",
        "performance-optimization",
        "code-quality",
        "technical-debt"
    ]

    # Configurações específicas
    security_analysis_enabled: bool = True
    architecture_review_enabled: bool = True
    complexity_threshold_high: float = 0.8
    complexity_threshold_low: float = 0.3
