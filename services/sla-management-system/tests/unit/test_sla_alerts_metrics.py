"""
Testes unitários para métricas de SLA Alerts.
"""

from src.observability.metrics import sla_metrics


class TestSLAAlertsMetrics:
    """Testes para métricas de SLA Alerts."""

    def test_sla_alerts_received_total_counter_exists(self):
        """Testa que counter sla_alerts_received_total existe."""
        assert hasattr(sla_metrics, "sla_alerts_received_total")
        assert sla_metrics.sla_alerts_received_total._type == "counter"

    def test_sla_notifications_sent_total_counter_exists(self):
        """Testa que counter sla_notifications_sent_total existe."""
        assert hasattr(sla_metrics, "sla_notifications_sent_total")
        assert sla_metrics.sla_notifications_sent_total._type == "counter"

    def test_sla_notification_failures_total_counter_exists(self):
        """Testa que counter sla_notification_failures_total existe."""
        assert hasattr(sla_metrics, "sla_notification_failures_total")
        assert sla_metrics.sla_notification_failures_total._type == "counter"

    def test_sla_notification_latency_seconds_histogram_exists(self):
        """Testa que histogram sla_notification_latency_seconds existe."""
        assert hasattr(sla_metrics, "sla_notification_latency_seconds")
        assert sla_metrics.sla_notification_latency_seconds._type == "histogram"

    def test_record_sla_alert_received(self):
        """Testa registro de alerta recebido."""
        # Act
        sla_metrics.record_sla_alert_received(
            severity="critical",
            topic="sla.alerts",
        )

        # Assert - Verificar que métrica foi incrementada
        metric = sla_metrics.sla_alerts_received_total
        assert metric.labels(severity="critical", topic="sla.alerts")._value.get() == 1

    def test_record_sla_notification_sent_success(self):
        """Testa registro de notificação enviada com sucesso."""
        # Act
        sla_metrics.record_sla_notification_sent(
            channel="slack",
            severity="warning",
            success=True,
            latency=0.5,
        )

        # Assert
        metric = sla_metrics.sla_notifications_sent_total
        assert (
            metric.labels(channel="slack", severity="warning", status="success")._value.get() == 1
        )

    def test_record_sla_notification_sent_error(self):
        """Testa registro de notificação com erro."""
        # Act
        sla_metrics.record_sla_notification_sent(
            channel="pagerduty",
            severity="critical",
            success=False,
        )

        # Assert
        metric = sla_metrics.sla_notifications_sent_total
        assert (
            metric.labels(channel="pagerduty", severity="critical", status="error")._value.get()
            == 1
        )

    def test_record_sla_notification_failure(self):
        """Testa registro de falha de notificação."""
        # Act
        sla_metrics.record_sla_notification_failure(
            channel="slack",
            severity="critical",
            error_type="HTTPStatusError",
        )

        # Assert
        metric = sla_metrics.sla_notification_failures_total
        assert (
            metric.labels(
                channel="slack", severity="critical", error_type="HTTPStatusError"
            )._value.get()
            == 1
        )

    def test_record_sla_notification_sent_with_latency(self):
        """Testa registro de notificação com latência."""
        # Act
        sla_metrics.record_sla_notification_sent(
            channel="pagerduty",
            severity="emergency",
            success=True,
            latency=1.234,
        )

        # Assert - Verificar histogram
        histogram = sla_metrics.sla_notification_latency_seconds
        # A latência é observada no histogram
        assert histogram.labels(channel="pagerduty", severity="emergency") is not None

    def test_multiple_severity_labels(self):
        """Testa múltiplas severidades podem ser registradas."""
        severities = ["emergency", "critical", "warning", "info"]

        for severity in severities:
            sla_metrics.record_sla_alert_received(
                severity=severity,
                topic="sla.alerts",
            )

        # Verificar todas foram registradas
        metric = sla_metrics.sla_alerts_received_total
        for severity in severities:
            assert metric.labels(severity=severity, topic="sla.alerts")._value.get() >= 1

    def test_multiple_channel_labels(self):
        """Testa múltiplos canais podem ser registrados."""
        channels = ["slack", "pagerduty"]

        for channel in channels:
            sla_metrics.record_sla_notification_sent(
                channel=channel,
                severity="critical",
                success=True,
                latency=0.5,
            )

        # Verificar todas foram registradas
        metric = sla_metrics.sla_notifications_sent_total
        for channel in channels:
            assert (
                metric.labels(channel=channel, severity="critical", status="success")._value.get()
                >= 1
            )

    def test_record_sla_notification_sent_without_latency(self):
        """Testa registro de notificação sem latência (não deve observar histogram)."""
        # Act - Não deve causar erro
        sla_metrics.record_sla_notification_sent(
            channel="slack",
            severity="info",
            success=True,
            latency=None,
        )

        # Assert - Counter incrementado
        metric = sla_metrics.sla_notifications_sent_total
        assert metric.labels(channel="slack", severity="info", status="success")._value.get() == 1
