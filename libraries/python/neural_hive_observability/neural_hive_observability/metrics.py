"""
Métricas padronizadas para Neural Hive-Mind.

Implementa métricas Prometheus consistentes seguindo esquema padronizado
com labels neural_hive_component, neural_hive_layer, domain, channel, status.
"""

import logging
from typing import Optional, Dict, List
from prometheus_client import (
    Counter, Histogram, Gauge, Info,
    start_http_server, CollectorRegistry, REGISTRY
)

from .config import ObservabilityConfig

logger = logging.getLogger(__name__)


class NeuralHiveMetrics:
    """Conjunto padronizado de métricas do Neural Hive-Mind."""

    _instance: Optional['NeuralHiveMetrics'] = None
    _registry: Optional[CollectorRegistry] = None

    def __new__(cls, config: ObservabilityConfig, registry: Optional[CollectorRegistry] = None):
        """Singleton pattern para evitar duplicação de métricas."""
        if cls._instance is not None:
            logger.debug("Retornando instância existente de NeuralHiveMetrics")
            return cls._instance
        return super().__new__(cls)

    def __init__(self, config: ObservabilityConfig, registry: Optional[CollectorRegistry] = None):
        """
        Inicializa métricas padronizadas.

        Args:
            config: Configuração de observabilidade
            registry: Registry Prometheus (opcional, usa dedicado)
        """
        if NeuralHiveMetrics._instance is not None:
            return

        self.config = config
        # Usar registry dedicado para evitar conflitos
        if NeuralHiveMetrics._registry is None:
            NeuralHiveMetrics._registry = CollectorRegistry()
        self.registry = registry or NeuralHiveMetrics._registry
        self._common_labels = list(config.common_labels.keys())
        self._common_label_values = list(config.common_labels.values())
        NeuralHiveMetrics._instance = self

        # Inicializar métricas
        self._init_service_metrics()
        self._init_request_metrics()
        self._init_intent_metrics()
        self._init_plan_metrics()
        self._init_infrastructure_metrics()
        self._init_tracing_export_metrics()
        self._init_slo_metrics()

    def _init_service_metrics(self):
        """Inicializa métricas de serviço."""
        # Info sobre o serviço
        self.service_info = Info(
            "neural_hive_service",
            "Informações do serviço Neural Hive-Mind",
            registry=self.registry
        )
        self.service_info.info({
            "service_name": self.config.service_name,
            "version": self.config.service_version,
            "component": self.config.neural_hive_component,
            "layer": self.config.neural_hive_layer,
            "domain": self.config.neural_hive_domain or "unknown"
        })

        # Startup counter
        self.service_startup_total = Counter(
            "neural_hive_service_startup_total",
            "Total de inicializações do serviço",
            self._common_labels,
            registry=self.registry
        )

    def _init_request_metrics(self):
        """Inicializa métricas de requisições."""
        # Total de requisições
        self.neural_hive_requests_total = Counter(
            "neural_hive_requests_total",
            "Total de requisições processadas",
            self._common_labels + ["channel", "status"],
            registry=self.registry
        )

        # Duração de requisições (Fluxo A - Captura)
        # IMPORTANT: Using coarse-grained labels only to prevent high cardinality
        # intent_id and plan_id are NOT used as labels - use trace_id exemplars instead
        self.neural_hive_captura_duration_seconds = Histogram(
            "neural_hive_captura_duration_seconds",
            "Duração da captura de intenções",
            self._common_labels + ["channel"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=self.registry
        )

        # Duração de geração de planos (Fluxo B)
        self.neural_hive_geracao_duration_seconds = Histogram(
            "neural_hive_geracao_duration_seconds",
            "Duração da geração de planos",
            self._common_labels + ["channel"],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry
        )

        # Duração de orquestração (Fluxo C)
        self.neural_hive_orquestracao_duration_seconds = Histogram(
            "neural_hive_orquestracao_duration_seconds",
            "Duração da orquestração de planos",
            self._common_labels + ["channel"],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0],
            registry=self.registry
        )

    def _init_intent_metrics(self):
        """Inicializa métricas de intenções."""
        # Intenções processadas
        self.intentions_processed_total = Counter(
            "neural_hive_intentions_processed_total",
            "Total de intenções processadas",
            self._common_labels + ["channel", "status"],
            registry=self.registry
        )

        # Distribuição de confiança
        self.intent_confidence_histogram = Histogram(
            "neural_hive_intent_confidence",
            "Distribuição de confiança das intenções",
            self._common_labels + ["channel"],
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            registry=self.registry
        )

        # Intenções com baixa confiança
        self.low_confidence_routed_total = Counter(
            "neural_hive_low_confidence_routed_total",
            "Intenções roteadas devido à baixa confiança",
            self._common_labels + ["channel", "route_target"],
            registry=self.registry
        )

    def _init_plan_metrics(self):
        """Inicializa métricas de planos."""
        # Planos gerados
        self.plans_generated_total = Counter(
            "neural_hive_plans_generated_total",
            "Total de planos gerados",
            self._common_labels + ["channel", "status"],
            registry=self.registry
        )

        # Duração de execução de planos
        self.plan_execution_duration_seconds = Histogram(
            "neural_hive_plan_execution_duration_seconds",
            "Duração da execução de planos",
            self._common_labels + ["channel", "plan_type"],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, 1800.0],
            registry=self.registry
        )

        # Sucesso na execução de planos
        self.plan_execution_success_rate = Gauge(
            "neural_hive_plan_execution_success_rate",
            "Taxa de sucesso na execução de planos",
            self._common_labels + ["channel"],
            registry=self.registry
        )

    def _init_infrastructure_metrics(self):
        """Inicializa métricas de infraestrutura."""
        # Conexões ativas
        self.active_connections = Gauge(
            "neural_hive_active_connections_total",
            "Conexões ativas do serviço",
            self._common_labels + ["connection_type"],
            registry=self.registry
        )

        # Uso de memória
        self.memory_usage_bytes = Gauge(
            "neural_hive_memory_usage_bytes",
            "Uso de memória do processo",
            self._common_labels,
            registry=self.registry
        )

        # Health status
        self.health_status = Gauge(
            "neural_hive_health_status",
            "Status de saúde do serviço (1=healthy, 0=unhealthy)",
            self._common_labels + ["check_name"],
            registry=self.registry
        )

    def _init_tracing_export_metrics(self):
        """Inicializa métricas de export de spans para monitoramento de tracing."""
        # Contador de falhas de export
        self.span_export_failures_total = Counter(
            "neural_hive_span_export_failures_total",
            "Total de falhas no export de spans",
            self._common_labels + ["error_type", "endpoint"],
            registry=self.registry
        )

        # Contador de exports bem-sucedidos
        self.span_export_success_total = Counter(
            "neural_hive_span_export_success_total",
            "Total de exports de spans bem-sucedidos",
            self._common_labels + ["endpoint"],
            registry=self.registry
        )

        # Histograma de duração de export
        self.span_export_duration_seconds = Histogram(
            "neural_hive_span_export_duration_seconds",
            "Duração do export de spans em segundos",
            self._common_labels + ["endpoint", "result"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
            registry=self.registry
        )

        # Gauge para tamanho da fila de spans pendentes
        self.span_export_queue_size = Gauge(
            "neural_hive_span_export_queue_size",
            "Tamanho atual da fila de spans pendentes para export",
            self._common_labels,
            registry=self.registry
        )

    def _init_slo_metrics(self):
        """Inicializa métricas específicas para SLOs."""
        # Availability SLO
        self.slo_availability_ratio = Gauge(
            "neural_hive_slo_availability_ratio",
            "Taxa de disponibilidade para SLO (0.0-1.0)",
            self._common_labels + ["slo_name"],
            registry=self.registry
        )

        # Latency SLO
        self.slo_latency_percentile = Gauge(
            "neural_hive_slo_latency_percentile_seconds",
            "Percentil de latência para SLO",
            self._common_labels + ["slo_name", "percentile"],
            registry=self.registry
        )

        # Error budget
        self.slo_error_budget_remaining = Gauge(
            "neural_hive_slo_error_budget_remaining_ratio",
            "Error budget restante para SLO (0.0-1.0)",
            self._common_labels + ["slo_name"],
            registry=self.registry
        )

        # Error budget burn rate
        self.slo_error_budget_burn_rate = Gauge(
            "neural_hive_slo_error_budget_burn_rate",
            "Taxa de queima do error budget",
            self._common_labels + ["slo_name", "window"],
            registry=self.registry
        )

        # Cache performance metrics
        self.cache_hits_total = Counter(
            "neural_hive_cache_hits_total",
            "Total de cache hits",
            self._common_labels + ["cache_name"],
            registry=self.registry
        )

        self.cache_misses_total = Counter(
            "neural_hive_cache_misses_total",
            "Total de cache misses",
            self._common_labels + ["cache_name"],
            registry=self.registry
        )

        self.cache_evictions_total = Counter(
            "neural_hive_cache_evictions_total",
            "Total de evicções de cache",
            self._common_labels + ["cache_name"],
            registry=self.registry
        )

        # Queue depth metrics
        self.queue_depth = Gauge(
            "neural_hive_queue_depth",
            "Profundidade atual da fila",
            self._common_labels + ["queue_name"],
            registry=self.registry
        )

        self.queue_processing_lag_seconds = Gauge(
            "neural_hive_queue_processing_lag_seconds",
            "Lag de processamento da fila em segundos",
            self._common_labels + ["queue_name"],
            registry=self.registry
        )

    def increment_requests(self, channel: str = "unknown", status: str = "success"):
        """Incrementa contador de requisições."""
        self.neural_hive_requests_total.labels(
            *self._common_label_values, channel, status
        ).inc()

    def observe_with_exemplar(self, metric, value: float, labels: List[str], exemplar_data: Optional[Dict[str, str]] = None):
        """
        Observa métrica com suporte a exemplars para correlação.

        Args:
            metric: Métrica Prometheus (Histogram)
            value: Valor a observar
            labels: Lista de valores de labels
            exemplar_data: Dados do exemplar (ex: {"trace_id": "123", "span_id": "456"})
        """
        histogram = metric.labels(*labels)

        if exemplar_data:
            try:
                # Tentar usar exemplars se disponível (prometheus_client >= 0.14.0)
                histogram.observe(value, exemplar=exemplar_data)
                return
            except (TypeError, AttributeError):
                # Fallback para versões mais antigas
                pass

        # Observação padrão sem exemplar
        histogram.observe(value)

    def observe_captura_duration(self, duration: float, channel: str = "unknown", trace_id: Optional[str] = None, span_id: Optional[str] = None):
        """
        Observa duração de captura de intenção com exemplar para correlação.

        Args:
            duration: Duração em segundos
            channel: Canal de captura
            trace_id: ID do trace para exemplar
            span_id: ID do span para exemplar adicional
        """
        labels = [*self._common_label_values, channel]
        exemplar_data = {}

        if trace_id:
            exemplar_data["trace_id"] = trace_id
        if span_id:
            exemplar_data["span_id"] = span_id

        self.observe_with_exemplar(
            self.neural_hive_captura_duration_seconds,
            duration,
            labels,
            exemplar_data if exemplar_data else None
        )

    def observe_geracao_duration(self, duration: float, channel: str = "unknown", trace_id: Optional[str] = None, span_id: Optional[str] = None):
        """Observa duração de geração de planos com exemplar."""
        labels = [*self._common_label_values, channel]
        exemplar_data = {}

        if trace_id:
            exemplar_data["trace_id"] = trace_id
        if span_id:
            exemplar_data["span_id"] = span_id

        self.observe_with_exemplar(
            self.neural_hive_geracao_duration_seconds,
            duration,
            labels,
            exemplar_data if exemplar_data else None
        )

    def observe_orquestracao_duration(self, duration: float, channel: str = "unknown", trace_id: Optional[str] = None, span_id: Optional[str] = None):
        """Observa duração de orquestração com exemplar."""
        labels = [*self._common_label_values, channel]
        exemplar_data = {}

        if trace_id:
            exemplar_data["trace_id"] = trace_id
        if span_id:
            exemplar_data["span_id"] = span_id

        self.observe_with_exemplar(
            self.neural_hive_orquestracao_duration_seconds,
            duration,
            labels,
            exemplar_data if exemplar_data else None
        )

    def increment_intentions(self, channel: str = "unknown", status: str = "success"):
        """Incrementa contador de intenções."""
        self.intentions_processed_total.labels(
            *self._common_label_values, channel, status
        ).inc()

    def observe_intent_confidence(self, confidence: float, channel: str = "unknown"):
        """Observa confiança de intenção."""
        self.intent_confidence_histogram.labels(
            *self._common_label_values, channel
        ).observe(confidence)

    def increment_low_confidence_routed(self, channel: str = "unknown", route_target: str = "human"):
        """Incrementa contador de baixa confiança."""
        self.low_confidence_routed_total.labels(
            *self._common_label_values, channel, route_target
        ).inc()

    def increment_plans(self, channel: str = "unknown", status: str = "success"):
        """Incrementa contador de planos."""
        self.plans_generated_total.labels(
            *self._common_label_values, channel, status
        ).inc()

    def observe_plan_execution(self, duration: float, channel: str = "unknown", plan_type: str = "unknown"):
        """Observa duração de execução de plano."""
        self.plan_execution_duration_seconds.labels(
            *self._common_label_values, channel, plan_type
        ).observe(duration)

    def set_health_status(self, check_name: str, is_healthy: bool):
        """Define status de health check."""
        self.health_status.labels(
            *self._common_label_values, check_name
        ).set(1.0 if is_healthy else 0.0)

    def update_memory_usage(self, bytes_used: int):
        """Atualiza uso de memória."""
        self.memory_usage_bytes.labels(*self._common_label_values).set(bytes_used)

    def set_active_connections(self, connection_type: str, count: int):
        """Define número de conexões ativas."""
        self.active_connections.labels(
            *self._common_label_values, connection_type
        ).set(count)

    # SLO-specific methods
    def set_slo_availability(self, slo_name: str, availability_ratio: float):
        """Define taxa de disponibilidade para SLO."""
        self.slo_availability_ratio.labels(
            *self._common_label_values, slo_name
        ).set(availability_ratio)

    def set_slo_latency_percentile(self, slo_name: str, percentile: str, latency_seconds: float):
        """Define percentil de latência para SLO."""
        self.slo_latency_percentile.labels(
            *self._common_label_values, slo_name, percentile
        ).set(latency_seconds)

    def set_slo_error_budget_remaining(self, slo_name: str, remaining_ratio: float):
        """Define error budget restante para SLO."""
        self.slo_error_budget_remaining.labels(
            *self._common_label_values, slo_name
        ).set(remaining_ratio)

    def set_slo_error_budget_burn_rate(self, slo_name: str, window: str, burn_rate: float):
        """Define taxa de queima do error budget."""
        self.slo_error_budget_burn_rate.labels(
            *self._common_label_values, slo_name, window
        ).set(burn_rate)

    # Cache metrics methods
    def increment_cache_hits(self, cache_name: str):
        """Incrementa contador de cache hits."""
        self.cache_hits_total.labels(
            *self._common_label_values, cache_name
        ).inc()

    def increment_cache_misses(self, cache_name: str):
        """Incrementa contador de cache misses."""
        self.cache_misses_total.labels(
            *self._common_label_values, cache_name
        ).inc()

    def increment_cache_evictions(self, cache_name: str):
        """Incrementa contador de evicções de cache."""
        self.cache_evictions_total.labels(
            *self._common_label_values, cache_name
        ).inc()

    # Queue metrics methods
    def set_queue_depth(self, queue_name: str, depth: int):
        """Define profundidade da fila."""
        self.queue_depth.labels(
            *self._common_label_values, queue_name
        ).set(depth)

    def set_queue_processing_lag(self, queue_name: str, lag_seconds: float):
        """Define lag de processamento da fila."""
        self.queue_processing_lag_seconds.labels(
            *self._common_label_values, queue_name
        ).set(lag_seconds)

    def calculate_cache_hit_rate(self, cache_name: str) -> float:
        """Calcula taxa de hit do cache baseada nos contadores."""
        try:
            hits_metric = self.cache_hits_total.labels(*self._common_label_values, cache_name)
            misses_metric = self.cache_misses_total.labels(*self._common_label_values, cache_name)

            hits = hits_metric._value._value if hasattr(hits_metric, '_value') else 0
            misses = misses_metric._value._value if hasattr(misses_metric, '_value') else 0

            total = hits + misses
            return hits / total if total > 0 else 0.0
        except Exception:
            return 0.0

    # Tracing export metrics methods
    def increment_span_export_failures(self, error_type: str, endpoint: str):
        """Incrementa contador de falhas de export de spans."""
        self.span_export_failures_total.labels(
            *self._common_label_values, error_type, endpoint
        ).inc()

    def increment_span_export_success(self, endpoint: str):
        """Incrementa contador de exports de spans bem-sucedidos."""
        self.span_export_success_total.labels(
            *self._common_label_values, endpoint
        ).inc()

    def observe_span_export_duration(self, duration: float, endpoint: str, result: str):
        """Observa duração de export de spans."""
        self.span_export_duration_seconds.labels(
            *self._common_label_values, endpoint, result
        ).observe(duration)

    def set_span_export_queue_size(self, size: int):
        """Define tamanho da fila de spans pendentes."""
        self.span_export_queue_size.labels(*self._common_label_values).set(size)


# Métricas globais
_metrics: Optional[NeuralHiveMetrics] = None


def init_metrics(config: ObservabilityConfig) -> NeuralHiveMetrics:
    """
    Inicializa métricas globais.

    Args:
        config: Configuração de observabilidade

    Returns:
        Instância de métricas
    """
    global _metrics
    if _metrics is not None:
        logger.debug("Métricas já inicializadas, retornando instância existente")
        return _metrics
    _metrics = NeuralHiveMetrics(config)

    # Iniciar servidor Prometheus se configurado
    if config.prometheus_port > 0:
        try:
            start_http_server(config.prometheus_port, registry=_metrics.registry)
            logger.info(f"Servidor Prometheus iniciado na porta {config.prometheus_port}")
        except Exception as e:
            logger.warning(f"Erro ao iniciar servidor Prometheus: {e}")

    return _metrics


def get_metrics() -> Optional[NeuralHiveMetrics]:
    """Retorna instância global de métricas."""
    return _metrics