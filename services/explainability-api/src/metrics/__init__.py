"""
Módulo de métricas Prometheus para Explainability API v3.

Métricas específicas para:
- Geração de explicações (duração, contagem)
- Consenso hierárquico (força, nível dominante)
- Análises contrafactuais (cenários, outcomes)
"""

from .v3_metrics import (
    # Métricas de geração
    v3_generation_duration,
    v3_explanations_generated,
    # Métricas de consenso
    consensus_strength_gauge,
    dominant_level_counter,
    # Métricas de contrafactuais
    counterfactual_outcome_counter,
    # Wrapper class
    V3Metrics,
)

__all__ = [
    "v3_generation_duration",
    "v3_explanations_generated",
    "consensus_strength_gauge",
    "dominant_level_counter",
    "counterfactual_outcome_counter",
    "V3Metrics",
]
