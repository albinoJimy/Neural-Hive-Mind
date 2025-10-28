"""
Configuração específica do Evolution Specialist.
"""

from typing import List
import sys
import os

# Adicionar biblioteca ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..', 'libraries/python'))

from neural_hive_specialists import SpecialistConfig


class EvolutionSpecialistConfig(SpecialistConfig):
    """Configuração do Evolution Specialist."""

    # Override defaults
    specialist_type: str = "evolution"
    service_name: str = "specialist-evolution"
    mlflow_experiment_name: str = "evolution-specialist"
    mlflow_model_name: str = "evolution-evaluator"

    # Domínios suportados
    supported_domains: List[str] = [
        "maintainability-analysis",
        "scalability-evaluation",
        "extensibility-design",
        "tech-debt-assessment",
        "architectural-evolution"
    ]

    # Configurações específicas
    maintainability_enabled: bool = True
    scalability_analysis_enabled: bool = True
    tech_debt_threshold_high: float = 0.7
    tech_debt_threshold_low: float = 0.3
