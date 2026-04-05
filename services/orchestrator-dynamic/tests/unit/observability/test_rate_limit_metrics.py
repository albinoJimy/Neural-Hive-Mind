"""
Testes unitários para métricas de Rate Limiting.

Testa os contadores, histogramas e gauges Prometheus para rate limiting.
"""
from unittest.mock import MagicMock, patch

from observability.rate_limit_metrics import RateLimitMetrics, get_rate_limit_metrics


class TestRateLimitRequestsTotal:
    """Testes do Counter rate_limit_requests_total."""

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_counter_initialized(self, mock_gauge, mock_histogram, mock_counter):
        """Verifica que counter foi inicializado com labels corretas."""
        RateLimitMetrics()

        # Verifica que Counter foi chamado
        calls = [
            c
            for c in mock_counter.call_args_list
            if "rate_limit_requests_total" in str(c)
        ]
        assert len(calls) == 1

        # Verifica labels
        call_args = str(calls[0])
        assert "service" in call_args
        assert "tenant_id" in call_args
        assert "endpoint" in call_args
        assert "status" in call_args

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_record_request_allowed(self, mock_gauge, mock_histogram, mock_counter):
        """Testa registro de request permitida."""
        metrics = RateLimitMetrics()
        mock_labels = MagicMock()
        metrics.rate_limit_requests_total.labels = MagicMock(return_value=mock_labels)

        metrics.record_request(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            endpoint="/api/v1/workflows",
            status="allowed",
        )

        metrics.rate_limit_requests_total.labels.assert_called_once_with(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            endpoint="/api/v1/workflows",
            status="allowed",
        )
        mock_labels.inc.assert_called_once()

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_record_request_throttled(self, mock_gauge, mock_histogram, mock_counter):
        """Testa registro de request throttled."""
        metrics = RateLimitMetrics()
        mock_labels = MagicMock()
        metrics.rate_limit_requests_total.labels = MagicMock(return_value=mock_labels)

        metrics.record_request(
            service="orchestrator-dynamic",
            tenant_id="tenant-456",
            endpoint="/api/v1/predict",
            status="throttled",
        )

        metrics.rate_limit_requests_total.labels.assert_called_once_with(
            service="orchestrator-dynamic",
            tenant_id="tenant-456",
            endpoint="/api/v1/predict",
            status="throttled",
        )
        mock_labels.inc.assert_called_once()


class TestRateLimitWaitDuration:
    """Testes do Histogram rate_limit_wait_duration_seconds."""

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_histogram_initialized(self, mock_gauge, mock_histogram, mock_counter):
        """Verifica que histogram foi inicializado com buckets corretas."""
        RateLimitMetrics()

        calls = [
            c
            for c in mock_histogram.call_args_list
            if "rate_limit_wait_duration_seconds" in str(c)
        ]
        assert len(calls) == 1

        # Verifica buckets
        call_args = str(calls[0])
        assert "0.001" in call_args
        assert "0.005" in call_args
        assert "0.01" in call_args
        assert "0.025" in call_args
        assert "0.05" in call_args
        assert "0.1" in call_args
        assert "0.25" in call_args
        assert "0.5" in call_args
        assert "1.0" in call_args

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_record_wait_duration(self, mock_gauge, mock_histogram, mock_counter):
        """Testa registro de duração de espera."""
        metrics = RateLimitMetrics()
        mock_labels = MagicMock()
        metrics.rate_limit_wait_duration_seconds.labels = MagicMock(
            return_value=mock_labels
        )

        metrics.record_wait_duration(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            duration_seconds=0.023,
        )

        metrics.rate_limit_wait_duration_seconds.labels.assert_called_once_with(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
        )
        mock_labels.observe.assert_called_once_with(0.023)

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_record_wait_duration_zero(self, mock_gauge, mock_histogram, mock_counter):
        """Testa registro de espera zero (sem espera)."""
        metrics = RateLimitMetrics()
        mock_labels = MagicMock()
        metrics.rate_limit_wait_duration_seconds.labels = MagicMock(
            return_value=mock_labels
        )

        metrics.record_wait_duration(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            duration_seconds=0.0,
        )

        mock_labels.observe.assert_called_once_with(0.0)


class TestRateLimitTokensRemaining:
    """Testes do Gauge rate_limit_tokens_remaining."""

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_gauge_initialized(self, mock_gauge, mock_histogram, mock_counter):
        """Verifica que gauge foi inicializado com labels corretas."""
        RateLimitMetrics()

        calls = [
            c
            for c in mock_gauge.call_args_list
            if "rate_limit_tokens_remaining" in str(c)
        ]
        assert len(calls) == 1

        # Verifica labels
        call_args = str(calls[0])
        assert "service" in call_args
        assert "tenant_id" in call_args
        assert "user_id" in call_args
        assert "endpoint" in call_args

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_set_tokens_remaining(self, mock_gauge, mock_histogram, mock_counter):
        """Testa setting de tokens restantes."""
        metrics = RateLimitMetrics()
        mock_labels = MagicMock()
        metrics.rate_limit_tokens_remaining.labels = MagicMock(return_value=mock_labels)

        metrics.set_tokens_remaining(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/workflows",
            tokens=42.0,
        )

        metrics.rate_limit_tokens_remaining.labels.assert_called_once_with(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/workflows",
        )
        mock_labels.set.assert_called_once_with(42.0)

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_set_tokens_remaining_zero(self, mock_gauge, mock_histogram, mock_counter):
        """Testa setting de tokens zerado (bucket vazio)."""
        metrics = RateLimitMetrics()
        mock_labels = MagicMock()
        metrics.rate_limit_tokens_remaining.labels = MagicMock(return_value=mock_labels)

        metrics.set_tokens_remaining(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            user_id="user-789",
            endpoint="/api/v1/predict",
            tokens=0.0,
        )

        mock_labels.set.assert_called_once_with(0.0)


class TestRateLimitThrottleTotal:
    """Testes do Counter rate_limit_throttle_total."""

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_throttle_counter_initialized(
        self, mock_gauge, mock_histogram, mock_counter
    ):
        """Verifica que counter de throttle foi inicializado."""
        RateLimitMetrics()

        calls = [
            c
            for c in mock_counter.call_args_list
            if "rate_limit_throttle_total" in str(c)
        ]
        assert len(calls) == 1

        # Verifica labels
        call_args = str(calls[0])
        assert "service" in call_args
        assert "tenant_id" in call_args
        assert "reason" in call_args

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_record_throttle_capacity_exceeded(
        self, mock_gauge, mock_histogram, mock_counter
    ):
        """Testa registro de throttle por capacidade excedida."""
        metrics = RateLimitMetrics()
        mock_labels = MagicMock()
        metrics.rate_limit_throttle_total.labels = MagicMock(return_value=mock_labels)

        metrics.record_throttle(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            reason="capacity_exceeded",
        )

        metrics.rate_limit_throttle_total.labels.assert_called_once_with(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            reason="capacity_exceeded",
        )
        mock_labels.inc.assert_called_once()

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_record_throttle_tier_limit(self, mock_gauge, mock_histogram, mock_counter):
        """Testa registro de throttle por limite de tier."""
        metrics = RateLimitMetrics()
        mock_labels = MagicMock()
        metrics.rate_limit_throttle_total.labels = MagicMock(return_value=mock_labels)

        metrics.record_throttle(
            service="orchestrator-dynamic",
            tenant_id="tenant-free",
            reason="tier_limit",
        )

        metrics.rate_limit_throttle_total.labels.assert_called_once_with(
            service="orchestrator-dynamic",
            tenant_id="tenant-free",
            reason="tier_limit",
        )
        mock_labels.inc.assert_called_once()

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_record_throttle_burst_exceeded(
        self, mock_gauge, mock_histogram, mock_counter
    ):
        """Testa registro de throttle por burst excedido."""
        metrics = RateLimitMetrics()
        mock_labels = MagicMock()
        metrics.rate_limit_throttle_total.labels = MagicMock(return_value=mock_labels)

        metrics.record_throttle(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            reason="burst_exceeded",
        )

        metrics.rate_limit_throttle_total.labels.assert_called_once_with(
            service="orchestrator-dynamic",
            tenant_id="tenant-123",
            reason="burst_exceeded",
        )
        mock_labels.inc.assert_called_once()


class TestRateLimitMetricsSingleton:
    """Testes do singleton get_rate_limit_metrics."""

    @patch("observability.rate_limit_metrics.Counter")
    @patch("observability.rate_limit_metrics.Histogram")
    @patch("observability.rate_limit_metrics.Gauge")
    def test_singleton_returns_same_instance(
        self, mock_gauge, mock_histogram, mock_counter
    ):
        """Verifica que singleton retorna mesma instância."""
        metrics1 = get_rate_limit_metrics()
        metrics2 = get_rate_limit_metrics()

        assert metrics1 is metrics2

    def test_singleton_cached(self):
        """Verifica que singleton é cacheado (lru_cache)."""
        # Verifica que é decorado com lru_cache
        assert hasattr(get_rate_limit_metrics, "cache_info")
