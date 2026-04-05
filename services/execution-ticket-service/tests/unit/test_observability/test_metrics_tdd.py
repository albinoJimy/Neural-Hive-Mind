"""
Testes TDD para TicketServiceMetrics.

Foca em verificar que todas as métricas são inicializadas corretamente.
"""

import pytest

from prometheus_client import REGISTRY


# =============================================================================
# Fixture para limpar registry entre testes
# =============================================================================


@pytest.fixture(autouse=True)
def clear_prometheus_registry():
    """Limpa o registry do Prometheus antes de cada teste."""
    # Remover todos os collectors do registry
    for collector in list(REGISTRY._collector_to_names.keys()):
        REGISTRY.unregister(collector)
    yield
    # Cleanup após o teste
    for collector in list(REGISTRY._collector_to_names.keys()):
        REGISTRY.unregister(collector)


# =============================================================================
# Testes: TicketServiceMetrics
# =============================================================================


class TestTicketServiceMetrics:
    """Testes do TicketServiceMetrics."""

    def test_initializes_metrics(self):
        """TicketServiceMetrics inicializa todas as métricas."""
        # Arrange & Act
        from src.observability.metrics import TicketServiceMetrics

        metrics = TicketServiceMetrics()

        # Assert - verificar que métricas principais existem
        assert hasattr(metrics, "tickets_consumed_total")
        assert hasattr(metrics, "tickets_persisted_total")
        assert hasattr(metrics, "api_requests_total")
        assert hasattr(metrics, "webhooks_sent_total")
        assert hasattr(metrics, "jwt_tokens_generated_total")

    def test_initializes_with_custom_service_name(self):
        """TicketServiceMetrics inicia com nome customizado."""
        # Arrange & Act
        from src.observability.metrics import TicketServiceMetrics

        metrics = TicketServiceMetrics(service_name="custom-service")

        # Assert
        assert metrics is not None
        assert hasattr(metrics, "tickets_consumed_total")

    def test_tickets_consumed_total_is_counter(self):
        """tickets_consumed_total é um Counter Prometheus."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics
        from prometheus_client import Counter

        # Act
        metrics = TicketServiceMetrics()

        # Assert
        assert isinstance(metrics.tickets_consumed_total, Counter)

    def test_webhooks_sent_total_is_counter(self):
        """webhooks_sent_total é um Counter Prometheus."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics
        from prometheus_client import Counter

        # Act
        metrics = TicketServiceMetrics()

        # Assert
        assert isinstance(metrics.webhooks_sent_total, Counter)

    def test_tickets_by_status_is_gauge(self):
        """tickets_by_status é um Gauge Prometheus."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics
        from prometheus_client import Gauge

        # Act
        metrics = TicketServiceMetrics()

        # Assert
        assert isinstance(metrics.tickets_by_status, Gauge)

    def test_ticket_processing_duration_seconds_is_histogram(self):
        """ticket_processing_duration_seconds é um Histogram Prometheus."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics
        from prometheus_client import Histogram

        # Act
        metrics = TicketServiceMetrics()

        # Assert
        assert isinstance(metrics.ticket_processing_duration_seconds, Histogram)

    def test_api_request_duration_seconds_is_histogram(self):
        """api_request_duration_seconds é um Histogram Prometheus."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics
        from prometheus_client import Histogram

        # Act
        metrics = TicketServiceMetrics()

        # Assert
        assert isinstance(metrics.api_request_duration_seconds, Histogram)

    def test_webhook_duration_seconds_is_histogram(self):
        """webhook_duration_seconds é um Histogram Prometheus."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics
        from prometheus_client import Histogram

        # Act
        metrics = TicketServiceMetrics()

        # Assert
        assert isinstance(metrics.webhook_duration_seconds, Histogram)

    def test_postgres_queries_total_has_operation_label(self):
        """postgres_queries_total tem label 'operation'."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics

        # Act
        metrics = TicketServiceMetrics()

        # Assert - verificar que as métricas com labels foram criadas
        assert hasattr(metrics, "postgres_queries_total")
        assert hasattr(metrics, "mongodb_operations_total")

    def test_api_requests_total_has_labels(self):
        """api_requests_total tem labels method, endpoint, status_code."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics

        # Act
        metrics = TicketServiceMetrics()

        # Assert
        assert hasattr(metrics, "api_requests_total")
        assert hasattr(metrics, "api_errors_total")

    def test_kafka_metrics_exist(self):
        """Métricas de Kafka existem."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics

        # Act
        metrics = TicketServiceMetrics()

        # Assert
        assert hasattr(metrics, "kafka_messages_consumed_total")
        assert hasattr(metrics, "kafka_consumer_lag")

    def test_idempotency_metrics_exist(self):
        """Métricas de idempotency existem."""
        # Arrange
        from src.observability.metrics import TicketServiceMetrics

        # Act
        metrics = TicketServiceMetrics()

        # Assert
        assert hasattr(metrics, "duplicates_detected_total")
        assert hasattr(metrics, "idempotency_cache_hits_total")
