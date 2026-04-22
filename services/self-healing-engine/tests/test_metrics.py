"""
Testes para o módulo de métricas Prometheus.

NOTA: As metrics Prometheus são definidas e registradas nos serviços individuais.
Este módulo testa apenas o MTTRTracker e a função get_metrics_text().
"""

import time

from src.metrics import MTTRTracker, get_metrics_text, mttr_tracker


class TestMTTRTracker:
    """Testes para o rastreador de MTTR."""

    def test_start_and_end_tracking(self):
        """Testa iniciar e finalizar rastreamento de incidente."""
        tracker = MTTRTracker()

        tracker.start_tracking("inc-1", "deadlock", "high")
        time.sleep(0.1)  # Pequena espera
        mttr_seconds = tracker.end_tracking("inc-1", "deadlock", "high")

        assert mttr_seconds >= 0.1
        assert mttr_seconds < 1.0  # Não deve levar muito tempo

    def test_get_average_mttr(self):
        """Testa calcular MTTR médio."""
        tracker = MTTRTracker()

        tracker.start_tracking("inc-1", "deadlock", "high")
        time.sleep(0.05)
        tracker.end_tracking("inc-1", "deadlock", "high")

        tracker.start_tracking("inc-2", "deadlock", "high")
        time.sleep(0.05)
        tracker.end_tracking("inc-2", "deadlock", "high")

        avg_mttr = tracker.get_average_mttr(incident_type="deadlock", severity="high")

        assert avg_mttr >= 0.05  # Ajustado para o valor real
        assert avg_mttr < 0.5

    def test_get_resolution_count(self):
        """Testa contar incidentes resolvidos."""
        tracker = MTTRTracker()

        tracker.start_tracking("inc-1", "deadlock", "high")
        tracker.end_tracking("inc-1", "deadlock", "high")

        tracker.start_tracking("inc-2", "memory_leak", "medium")
        tracker.end_tracking("inc-2", "memory_leak", "medium")

        total_count = tracker.get_resolution_count()
        deadlock_count = tracker.get_resolution_count(incident_type="deadlock")
        memory_count = tracker.get_resolution_count(incident_type="memory_leak")

        assert total_count == 2
        assert deadlock_count == 1
        assert memory_count == 1

    def test_end_tracking_nonexistent_incident(self):
        """Testa finalizar incidente não existe retorna 0."""
        tracker = MTTRTracker()

        mttr_seconds = tracker.end_tracking("inc-999", "deadlock", "high")

        assert mttr_seconds == 0.0


class TestMetricsEndpoint:
    """Testes para o endpoint de métricas."""

    def test_get_metrics_text(self):
        """Testa obter texto de métricas."""
        metrics_text = get_metrics_text()

        assert isinstance(metrics_text, str)
        # A string pode estar vazia se não houver metrics registradas
        # O importante é que não lança exceção


class TestGlobalMTTRTracker:
    """Testes para o tracker global de MTTR."""

    def test_global_mttr_tracker(self):
        """Testa usar tracker global."""
        mttr_tracker.start_tracking("global-inc-1", "deadlock", "high")
        time.sleep(0.05)
        mttr_seconds = mttr_tracker.end_tracking("global-inc-1", "deadlock", "high")

        assert mttr_seconds >= 0.05

        # Cleanup
        # Remove incidente das resoluções se existir
        if mttr_tracker._incident_resolutions:
            mttr_tracker._incident_resolutions.pop()
