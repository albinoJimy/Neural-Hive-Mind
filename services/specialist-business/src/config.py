"""
Configuração específica do Business Specialist.
"""

from typing import List
import sys
import os

# Adicionar biblioteca ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..', 'libraries/python'))

from neural_hive_specialists import SpecialistConfig


class BusinessSpecialistConfig(SpecialistConfig):
    """Configuração do Business Specialist."""

    # Override defaults
    specialist_type: str = "business"
    service_name: str = "specialist-business"
    mlflow_experiment_name: str = "business-specialist"
    mlflow_model_name: str = "business-evaluator"

    # Domínios suportados
    supported_domains: List[str] = [
        "workflow-analysis",
        "kpi-evaluation",
        "cost-optimization",
        "process-mining",
        "demand-forecasting"
    ]

    # Configurações específicas
    process_mining_enabled: bool = True
    cost_analysis_enabled: bool = True
    kpi_threshold_high: float = 0.8
    kpi_threshold_low: float = 0.5
