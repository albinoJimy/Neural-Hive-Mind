"""
Configuração específica do Evolution Specialist.
"""

import os
import sys

# Adicionar biblioteca ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../..", "libraries/python"))

from neural_hive_specialists import SpecialistConfig


class EvolutionSpecialistConfig(SpecialistConfig):
    """Configuração do Evolution Specialist."""

    # Override defaults
    specialist_type: str = "evolution"
    service_name: str = "specialist-evolution"
    mlflow_experiment_name: str = "evolution-specialist"
    mlflow_model_name: str = "evolution-evaluator"

    # Domínios suportados
    supported_domains: list[str] = [
        "maintainability-analysis",
        "scalability-evaluation",
        "extensibility-design",
        "tech-debt-assessment",
        "architectural-evolution",
    ]

    # Configurações específicas
    maintainability_enabled: bool = True
    scalability_analysis_enabled: bool = True
    tech_debt_threshold_high: float = 0.7
    tech_debt_threshold_low: float = 0.3

    # Evolution Hooks - Meta-learning config
    # Activado em producao em 2026-03-30 (Epic G002 - GAP-02-05-06)
    # Pre-requisitos: evolution_hooks library implementada, testes E2E passando
    # ROLLBACK: Mudar para False e redeloyar specialist-evolution
    evolution_hooks_enabled: bool = True
    evolution_hooks_min_similar_patterns: int = 5
    evolution_hooks_max_adjustment: float = 0.05
    evolution_hooks_pattern_registry_db: str = "neural_hive"
