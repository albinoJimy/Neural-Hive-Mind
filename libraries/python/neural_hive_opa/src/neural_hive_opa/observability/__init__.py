"""
Módulo de observabilidade para neural_hive_opa.

Exporta funções para gerenciar métricas e registry Prometheus.
"""
from neural_hive_opa.observability.metrics import (
    get_opa_metrics,
    get_registry,
    init_opa_metrics,
    reset_opa_metrics,
)

__all__ = [
    "get_registry",
    "init_opa_metrics",
    "get_opa_metrics",
    "reset_opa_metrics",
]
