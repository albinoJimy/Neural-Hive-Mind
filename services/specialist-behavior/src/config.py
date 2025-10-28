"""
Configuração específica do Behavior Specialist.
"""

from typing import List
import sys
import os

# Adicionar biblioteca ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..', 'libraries/python'))

from neural_hive_specialists import SpecialistConfig


class BehaviorSpecialistConfig(SpecialistConfig):
    """Configuração do Behavior Specialist."""

    # Override defaults
    specialist_type: str = "behavior"
    service_name: str = "specialist-behavior"
    mlflow_experiment_name: str = "behavior-specialist"
    mlflow_model_name: str = "behavior-evaluator"

    # Domínios suportados
    supported_domains: List[str] = [
        "ux-analysis",
        "accessibility-evaluation",
        "usability-testing",
        "user-experience",
        "interaction-design"
    ]

    # Configurações específicas
    accessibility_wcag_level: str = "AA"
    usability_threshold_high: float = 0.8
    usability_threshold_low: float = 0.5
    response_time_threshold_ms: int = 300
    interaction_cost_threshold: float = 0.7
