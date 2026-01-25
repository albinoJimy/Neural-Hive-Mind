"""
Testes de performance para o Neural Hive Mind.

Este pacote contem testes de carga, analise de bottlenecks,
validacao de SLOs e geracao de relatorios de performance.
"""

from tests.performance.prometheus_client import PrometheusClient, MetricsSnapshot
from tests.performance.kubernetes_client import KubernetesClient, HPAStatus
from tests.performance.bottleneck_analyzer import BottleneckAnalyzer, Bottleneck
from tests.performance.slo_validator import SLOValidator, LoadTestMetrics
from tests.performance.report_generator import (
    PerformanceReportGenerator,
    PerformanceTestResults,
    generate_performance_report,
)

__all__ = [
    'PrometheusClient',
    'MetricsSnapshot',
    'KubernetesClient',
    'HPAStatus',
    'BottleneckAnalyzer',
    'Bottleneck',
    'SLOValidator',
    'LoadTestMetrics',
    'PerformanceReportGenerator',
    'PerformanceTestResults',
    'generate_performance_report',
]
