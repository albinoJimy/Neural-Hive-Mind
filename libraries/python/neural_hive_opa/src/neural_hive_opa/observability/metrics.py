"""
Módulo de observabilidade e métricas para neural_hive_opa.

Centraliza o registry Prometheus e integração com neural_hive_observability.
"""
from typing import Optional

from prometheus_client import CollectorRegistry

from neural_hive_opa.metrics import OPAMetrics

# Registry global para métricas OPA
_registry: Optional[CollectorRegistry] = None
_metrics: Optional[OPAMetrics] = None


def get_registry() -> CollectorRegistry:
    """
    Retorna o registry Prometheus para métricas OPA.

    Returns:
        CollectorRegistry: Registry Prometheus
    """
    global _registry
    if _registry is None:
        _registry = CollectorRegistry()
    return _registry


def init_opa_metrics(
    subsystem: str = "neural_hive",
    registry: Optional[CollectorRegistry] = None,
) -> OPAMetrics:
    """
    Inicializa métricas OPA globais.

    Args:
        subsystem: Nome do subsistema para labels
        registry: Registry Prometheus (opcional, usa global se não fornecido)

    Returns:
        OPAMetrics: Instância de métricas OPA
    """
    global _metrics, _registry

    if registry is not None:
        _registry = registry
    elif _registry is None:
        _registry = CollectorRegistry()

    if _metrics is None:
        _metrics = OPAMetrics(subsystem=subsystem, registry=_registry)

    return _metrics


def get_opa_metrics() -> Optional[OPAMetrics]:
    """
    Retorna instância global de métricas OPA.

    Returns:
        OPAMetrics ou None se não inicializado
    """
    return _metrics


def reset_opa_metrics() -> None:
    """Reseta métricas OPA globais (útil para testes)."""
    global _metrics, _registry
    _metrics = None
    _registry = None
