"""
Testes para o módulo metrics.py da biblioteca neural_hive_observability.

Este arquivo contém testes unitários para validar:
- NeuralHiveMetrics initialization
- Métodos de métricas de requests
- Métodos de métricas de intenções
- Métodos de métricas de planos
- Métricas de infraestrutura
- Métricas SLO
- Métricas de cache
- Métricas de fila
- Métricas de export de spans
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from prometheus_client import CollectorRegistry

from neural_hive_observability.config import ObservabilityConfig
from neural_hive_observability.metrics import (
    NeuralHiveMetrics,
    init_metrics,
    get_metrics,
)


class TestNeuralHiveMetricsInit:
    """Testes para inicialização de NeuralHiveMetrics."""

    def test_initialization_with_config(self):
        """Testa inicialização com configuração."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component",
            neural_hive_layer="test-layer"
        )

        metrics = NeuralHiveMetrics(config)

        assert metrics.config == config
        assert metrics.registry is not None

    def test_singleton_pattern(self):
        """Testa padrão singleton."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics1 = NeuralHiveMetrics(config)
        metrics2 = NeuralHiveMetrics(config)

        # Deve retornar a mesma instância
        assert metrics1 is metrics2

    def test_initialization_with_custom_registry(self):
        """Testa inicialização com registry customizado."""
        # Reset singleton primeiro
        NeuralHiveMetrics._instance = None
        NeuralHiveMetrics._registry = None

        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        custom_registry = CollectorRegistry()
        metrics = NeuralHiveMetrics(config, registry=custom_registry)

        # Nota: singleton usa registry de classe se já existe
        # Se foi a primeira criação, custom_registry é usado
        # Se já existe singleton, retorna instância existente
        assert metrics.registry is not None

    def test_creates_service_info_metric(self):
        """Testa que cria métrica de serviço."""
        config = ObservabilityConfig(
            service_name="test-service",
            service_version="1.0.0",
            neural_hive_component="test-component",
            neural_hive_layer="test-layer"
        )

        metrics = NeuralHiveMetrics(config)

        assert hasattr(metrics, "service_info")

    def test_creates_request_metrics(self):
        """Testa que cria métricas de request."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        assert hasattr(metrics, "neural_hive_requests_total")
        assert hasattr(metrics, "neural_hive_captura_duration_seconds")

    def test_creates_intent_metrics(self):
        """Testa que cria métricas de intenção."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        assert hasattr(metrics, "intentions_processed_total")
        assert hasattr(metrics, "intent_confidence_histogram")
        assert hasattr(metrics, "low_confidence_routed_total")

    def test_creates_plan_metrics(self):
        """Testa que cria métricas de plano."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        assert hasattr(metrics, "plans_generated_total")
        assert hasattr(metrics, "plan_execution_duration_seconds")
        assert hasattr(metrics, "plan_execution_success_rate")

    def test_creates_infrastructure_metrics(self):
        """Testa que cria métricas de infraestrutura."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        assert hasattr(metrics, "active_connections")
        assert hasattr(metrics, "memory_usage_bytes")
        assert hasattr(metrics, "health_status")

    def test_creates_slo_metrics(self):
        """Testa que cria métricas SLO."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        assert hasattr(metrics, "slo_availability_ratio")
        assert hasattr(metrics, "slo_latency_percentile")
        assert hasattr(metrics, "slo_error_budget_remaining")
        assert hasattr(metrics, "slo_error_budget_burn_rate")

    def test_creates_cache_metrics(self):
        """Testa que cria métricas de cache."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        assert hasattr(metrics, "cache_hits_total")
        assert hasattr(metrics, "cache_misses_total")
        assert hasattr(metrics, "cache_evictions_total")

    def test_creates_queue_metrics(self):
        """Testa que cria métricas de fila."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        assert hasattr(metrics, "queue_depth")
        assert hasattr(metrics, "queue_processing_lag_seconds")

    def test_creates_tracing_export_metrics(self):
        """Testa que cria métricas de export de tracing."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        assert hasattr(metrics, "span_export_failures_total")
        assert hasattr(metrics, "span_export_success_total")
        assert hasattr(metrics, "span_export_duration_seconds")
        assert hasattr(metrics, "span_export_queue_size")


class TestRequestMetrics:
    """Testes para métricas de requisições."""

    def test_increment_requests(self):
        """Testa incremento de requisições."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component",
            neural_hive_layer="test-layer"
        )

        metrics = NeuralHiveMetrics(config)

        # Não deve lançar exceção
        metrics.increment_requests(channel="web", status="success")
        metrics.increment_requests(channel="api", status="error")

    def test_increment_requests_with_default_channel(self):
        """Testa incremento com canal padrão."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.increment_requests()  # Canal "unknown" por padrão

    def test_observe_captura_duration(self):
        """Testa observação de duração de captura."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        # Não deve lançar exceção
        metrics.observe_captura_duration(0.5, channel="web")
        metrics.observe_captura_duration(1.2, channel="api")

    def test_observe_captura_duration_with_trace_exemplar(self):
        """Testa observação com exemplar de trace."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.observe_captura_duration(
            0.5,
            channel="web",
            trace_id="12345678901234567890123456789012",
            span_id="1234567890123456"
        )

    def test_observe_geracao_duration(self):
        """Testa observação de duração de geração."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.observe_geracao_duration(5.0, channel="web")

    def test_observe_orquestracao_duration(self):
        """Testa observação de duração de orquestração."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.observe_orquestracao_duration(30.0, channel="api")


class TestIntentMetrics:
    """Testes para métricas de intenção."""

    def test_increment_intentions(self):
        """Testa incremento de intenções."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.increment_intentions(channel="web", status="success")
        metrics.increment_intentions(channel="api", status="error")

    def test_observe_intent_confidence(self):
        """Testa observação de confiança de intenção."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.observe_intent_confidence(0.95, channel="web")
        metrics.observe_intent_confidence(0.5, channel="api")
        metrics.observe_intent_confidence(0.1, channel="mobile")

    def test_increment_low_confidence_routed(self):
        """Testa incremento de roteamento por baixa confiança."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.increment_low_confidence_routed(channel="web", route_target="human")
        metrics.increment_low_confidence_routed(channel="api", route_target="fallback")


class TestPlanMetrics:
    """Testes para métricas de plano."""

    def test_increment_plans(self):
        """Testa incremento de planos."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.increment_plans(channel="web", status="success")
        metrics.increment_plans(channel="api", status="error")

    def test_observe_plan_execution(self):
        """Testa observação de execução de plano."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.observe_plan_execution(
            duration=10.5,
            channel="web",
            plan_type="data_processing"
        )
        metrics.observe_plan_execution(
            duration=5.2,
            channel="api",
            plan_type="validation"
        )

    def test_set_plan_execution_success_rate(self):
        """Testa definição de taxa de sucesso."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.plan_execution_success_rate.labels(
            *metrics._common_label_values, "web"
        ).set(0.95)


class TestInfrastructureMetrics:
    """Testes para métricas de infraestrutura."""

    def test_set_active_connections(self):
        """Testa definição de conexões ativas."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.set_active_connections("mongodb", 10)
        metrics.set_active_connections("redis", 5)
        metrics.set_active_connections("kafka", 3)

    def test_update_memory_usage(self):
        """Testa atualização de uso de memória."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.update_memory_usage(1024 * 1024 * 100)  # 100 MB
        metrics.update_memory_usage(1024 * 1024 * 500)  # 500 MB

    def test_set_health_status(self):
        """Testa definição de status de saúde."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.set_health_status("database", True)
        metrics.set_health_status("cache", True)
        metrics.set_health_status("queue", False)


class TestSLOMetrics:
    """Testes para métricas SLO."""

    def test_set_slo_availability(self):
        """Testa definição de disponibilidade SLO."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.set_slo_availability("api-availability", 0.999)
        metrics.set_slo_availability("database-availability", 0.995)

    def test_set_slo_latency_percentile(self):
        """Testa definição de percentil de latência SLO."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.set_slo_latency_percentile("api-latency", "p50", 0.1)
        metrics.set_slo_latency_percentile("api-latency", "p95", 0.5)
        metrics.set_slo_latency_percentile("api-latency", "p99", 1.2)

    def test_set_slo_error_budget_remaining(self):
        """Testa definição de error budget restante."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.set_slo_error_budget_remaining("api-slo", 0.8)
        metrics.set_slo_error_budget_remaining("database-slo", 0.5)

    def test_set_slo_error_budget_burn_rate(self):
        """Testa definição de taxa de queima de error budget."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.set_slo_error_budget_burn_rate("api-slo", "1h", 0.5)
        metrics.set_slo_error_budget_burn_rate("api-slo", "24h", 2.0)


class TestCacheMetrics:
    """Testes para métricas de cache."""

    def test_increment_cache_hits(self):
        """Testa incremento de cache hits."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.increment_cache_hits("intent_cache")
        metrics.increment_cache_hits("plan_cache")

    def test_increment_cache_misses(self):
        """Testa incremento de cache misses."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.increment_cache_misses("intent_cache")
        metrics.increment_cache_misses("plan_cache")

    def test_increment_cache_evictions(self):
        """Testa incremento de evicções de cache."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.increment_cache_evictions("intent_cache")
        metrics.increment_cache_evictions("plan_cache")

    def test_calculate_cache_hit_rate(self):
        """Testa cálculo de taxa de hit de cache."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        # Incrementar hits e misses
        for _ in range(80):
            metrics.increment_cache_hits("test_cache")
        for _ in range(20):
            metrics.increment_cache_misses("test_cache")

        # Calcular taxa de hit
        hit_rate = metrics.calculate_cache_hit_rate("test_cache")

        # Taxa deve ser próxima de 0.8
        assert 0.7 <= hit_rate <= 0.9

    def test_calculate_cache_hit_rate_with_no_data(self):
        """Testa cálculo com nenhum dado."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        hit_rate = metrics.calculate_cache_hit_rate("empty_cache")

        # Deve retornar 0.0 sem dados
        assert hit_rate == 0.0


class TestQueueMetrics:
    """Testes para métricas de fila."""

    def test_set_queue_depth(self):
        """Testa definição de profundidade da fila."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.set_queue_depth("intent_queue", 10)
        metrics.set_queue_depth("plan_queue", 5)
        metrics.set_queue_depth("execution_queue", 0)

    def test_set_queue_processing_lag(self):
        """Testa definição de lag de processamento da fila."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.set_queue_processing_lag("intent_queue", 1.5)
        metrics.set_queue_processing_lag("plan_queue", 0.5)


class TestTracingExportMetrics:
    """Testes para métricas de export de tracing."""

    def test_increment_span_export_failures(self):
        """Testa incremento de falhas de export."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.increment_span_export_failures("ConnectionError", "otel-collector:4317")
        metrics.increment_span_export_failures("Timeout", "otel-collector:4317")

    def test_increment_span_export_success(self):
        """Testa incremento de exports bem-sucedidos."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.increment_span_export_success("otel-collector:4317")
        metrics.increment_span_export_success("otel-collector:4317")

    def test_observe_span_export_duration(self):
        """Testa observação de duração de export."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.observe_span_export_duration(0.1, "otel-collector:4317", "success")
        metrics.observe_span_export_duration(0.5, "otel-collector:4317", "failure")

    def test_set_span_export_queue_size(self):
        """Testa definição de tamanho da fila de export."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        metrics.set_span_export_queue_size(0)
        metrics.set_span_export_queue_size(100)
        metrics.set_span_export_queue_size(500)


class TestInitMetrics:
    """Testes para init_metrics."""

    def test_init_metrics_returns_instance(self):
        """Testa que init_metrics retorna instância."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component",
            prometheus_port=0  # Não iniciar servidor HTTP
        )

        metrics = init_metrics(config)

        assert metrics is not None
        assert isinstance(metrics, NeuralHiveMetrics)

    def test_init_metrics_singleton(self):
        """Testa que init_metrics retorna singleton."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component",
            prometheus_port=0
        )

        metrics1 = init_metrics(config)
        metrics2 = init_metrics(config)

        assert metrics1 is metrics2

    def test_init_metrics_starts_http_server_when_port_set(self):
        """Testa que inicia servidor HTTP quando porta configurada."""
        # Resetar o global _metrics para garantir nova inicialização
        import neural_hive_observability.metrics as metrics_module
        metrics_module._metrics = None
        # Reset singleton também
        NeuralHiveMetrics._instance = None
        NeuralHiveMetrics._registry = None

        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component",
            prometheus_port=9091
        )

        with patch('neural_hive_observability.metrics.start_http_server') as mock_server:
            init_metrics(config)
            mock_server.assert_called_once()


class TestGetMetrics:
    """Testes para get_metrics."""

    def test_get_metrics_returns_none_when_not_initialized(self):
        """Testa que retorna None quando não inicializado."""
        # Resetar módulo
        import neural_hive_observability.metrics as metrics_module
        metrics_module._metrics = None

        result = get_metrics()
        assert result is None

    def test_get_metrics_returns_instance_after_init(self):
        """Testa que retorna instância após inicialização."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component",
            prometheus_port=0
        )

        init_metrics(config)
        result = get_metrics()

        assert result is not None
        assert isinstance(result, NeuralHiveMetrics)


class TestObserveWithExemplar:
    """Testes para observe_with_exemplar."""

    def test_observe_with_exemplar_with_valid_data(self):
        """Testa observação com exemplar válido."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        histogram = metrics.neural_hive_captura_duration_seconds
        labels = [*metrics._common_label_values, "web"]
        exemplar_data = {"trace_id": "12345678901234567890123456789012"}

        # Não deve lançar exceção
        metrics.observe_with_exemplar(histogram, 0.5, labels, exemplar_data)

    def test_observe_with_exemplar_without_exemplar(self):
        """Testa observação sem exemplar."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        histogram = metrics.neural_hive_captura_duration_seconds
        labels = [*metrics._common_label_values, "web"]

        metrics.observe_with_exemplar(histogram, 0.5, labels, None)

    def test_observe_with_exemplar_with_empty_dict(self):
        """Testa observação com dicionário vazio."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        histogram = metrics.neural_hive_captura_duration_seconds
        labels = [*metrics._common_label_values, "web"]

        metrics.observe_with_exemplar(histogram, 0.5, labels, {})


class TestServiceStartupMetrics:
    """Testes para métricas de startup."""

    def test_service_startup_total_counter(self):
        """Testa contador de startups."""
        config = ObservabilityConfig(
            service_name="test-service",
            neural_hive_component="test-component"
        )

        metrics = NeuralHiveMetrics(config)

        # Incrementar contador
        metrics.service_startup_total.labels(**config.common_labels).inc()

        # Verificar que foi incrementado (não lança exceção)
        samples = list(metrics.service_startup_total.collect())
        assert len(samples) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
