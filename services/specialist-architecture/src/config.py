"""
Configuração específica do Architecture Specialist.
"""

from typing import List
import sys
import os

# Adicionar biblioteca ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..', 'libraries/python'))

from neural_hive_specialists import SpecialistConfig


class ArchitectureSpecialistConfig(SpecialistConfig):
    """Configuração do Architecture Specialist."""

    # Override defaults
    specialist_type: str = "architecture"
    service_name: str = "specialist-architecture"
    mlflow_experiment_name: str = "architecture-specialist"
    mlflow_model_name: str = "architecture-evaluator"

    # Domínios suportados
    supported_domains: List[str] = [
        "design-patterns",
        "solid-principles",
        "coupling-cohesion",
        "separation-of-concerns",
        "layering-modularity"
    ]

    # Configurações específicas
    design_patterns_enabled: bool = True
    solid_analysis_enabled: bool = True
    coupling_threshold_high: float = 0.7
    cohesion_threshold_low: float = 0.5
