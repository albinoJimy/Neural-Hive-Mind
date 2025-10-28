"""
Neural Hive-Mind Metrics Library

Biblioteca Python para métricas com suporte a exemplars e correlação distribuída.
Fornece instrumentação padronizada para componentes do Neural Hive-Mind.
"""

from .metrics import (
    NeuralHiveMetrics,
    BarramentoMetrics,
    CognicaoMetrics,
    ExperienciaMetrics,
    OrquestracaoMetrics,
    ExecucaoMetrics,
    ResilienciaMetrics,
)

from .correlation import (
    CorrelationContext,
    trace_correlation,
    with_correlation,
)

from .exemplars import (
    ExemplarCollector,
    create_exemplar,
)

from .config import (
    MetricsConfig,
    configure_metrics,
)

__version__ = "1.0.0"
__author__ = "Neural Hive-Mind Team"

__all__ = [
    # Core metrics classes
    "NeuralHiveMetrics",
    "BarramentoMetrics",
    "CognicaoMetrics",
    "ExperienciaMetrics",
    "OrquestracaoMetrics",
    "ExecucaoMetrics",
    "ResilienciaMetrics",

    # Correlation utilities
    "CorrelationContext",
    "trace_correlation",
    "with_correlation",

    # Exemplar support
    "ExemplarCollector",
    "create_exemplar",

    # Configuration
    "MetricsConfig",
    "configure_metrics",
]