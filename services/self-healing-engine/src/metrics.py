"""
Prometheus Metrics para Self-Healing Engine.

NOTA: Este módulo fornece funções helper e MTTRTracker para compatibilidade.
As metrics Prometheus são definidas e registradas nos serviços individuais:
- DetectionService: self_healing_deadlocks_detected_total, self_healing_memory_leaks_detected_total, etc.
- HealthMonitor: self_healing_health_checks_total, self_healing_kafka_lag_checks_total, etc.
- RemediationManager: self_healing_remediations_total, self_healing_mttr_seconds_total, etc.
- PlaybookExecutor: self_healing_playbook_execution_total, self_healing_opa_validation_total, etc.

Este módulo NÃO registra metrics para evitar colisões com os serviços.
"""

from datetime import UTC, datetime, timedelta

import structlog

logger = structlog.get_logger()


# Classe para rastrear MTTR
class MTTRTracker:
    """
    Rastreia Mean Time To Recover para incidentes.

    Calcula o tempo médio entre detecção e resolução de incidentes.
    """

    def __init__(self):
        self._incident_start_times: dict[str, datetime] = {}
        self._incident_resolutions: list[tuple[str, str, str, timedelta]] = []

    def start_tracking(self, incident_id: str, incident_type: str, severity: str):
        """Inicia rastreamento de incidente."""
        key = f"{incident_type}:{severity}:{incident_id}"
        self._incident_start_times[key] = datetime.now(UTC)

    def end_tracking(self, incident_id: str, incident_type: str, severity: str) -> float:
        """
        Finaliza rastreamento e retorna MTTR em segundos.

        Returns:
            MTTR em segundos
        """
        key = f"{incident_type}:{severity}:{incident_id}"
        start_time = self._incident_start_times.get(key)

        if start_time:
            duration = datetime.now(UTC) - start_time
            duration_seconds = duration.total_seconds()

            # Remove do rastreamento
            del self._incident_start_times[key]

            # Guarda para cálculos agregados
            self._incident_resolutions.append((incident_id, incident_type, severity, duration))

            return duration_seconds
        else:
            logger.warning(
                "mttr_tracker.incident_not_found",
                incident_id=incident_id,
                incident_type=incident_type,
            )
            return 0.0

    def get_average_mttr(self, incident_type: str = None, severity: str = None) -> float:
        """
        Retorna MTTR médio em segundos.

        Args:
            incident_type: Filtrar por tipo (opcional)
            severity: Filtrar por severidade (opcional)

        Returns:
            MTTR médio em segundos
        """
        filtered = self._incident_resolutions

        if incident_type:
            filtered = [r for r in filtered if r[1] == incident_type]
        if severity:
            filtered = [r for r in filtered if r[2] == severity]

        if not filtered:
            return 0.0

        total_seconds = sum(r[3].total_seconds() for r in filtered)
        return total_seconds / len(filtered)

    def get_resolution_count(self, incident_type: str = None, severity: str = None) -> int:
        """Retorna número de incidentes resolvidos."""
        filtered = self._incident_resolutions

        if incident_type:
            filtered = [r for r in filtered if r[1] == incident_type]
        if severity:
            filtered = [r for r in filtered if r[2] == severity]

        return len(filtered)


# Instância global do tracker
mttr_tracker = MTTRTracker()


def get_metrics_text() -> str:
    """
    Retorna todas as métricas em formato Prometheus text.

    NOTA: As metrics são registradas pelos serviços individuais.
    Esta função apenas exporta tudo do Prometheus Registry.

    Returns:
        String com métricas no formato Prometheus
    """
    from prometheus_client import REGISTRY, generate_latest

    return generate_latest(REGISTRY).decode("utf-8")


# 1775981852
