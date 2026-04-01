"""
Prometheus Metrics para Self-Healing Engine.

Exporta métricas sobre detecções, remediações, MTTR e circuit breakers.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict

import structlog
from prometheus_client import REGISTRY, Counter, Gauge, Histogram, Info

logger = structlog.get_logger()


# Métricas de Detecção
detection_events_total = Counter(
    "self_healing_detection_events_total",
    "Total de eventos de detecção",
    ["incident_type", "severity", "detected_by"],
)

detection_duration_seconds = Histogram(
    "self_healing_detection_duration_seconds",
    "Tempo para detectar incidente",
    ["incident_type"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

active_incidents = Gauge(
    "self_healing_active_incidents", "Número de incidentes ativos", ["incident_type", "severity"]
)

# Métricas de Remediação
remediation_events_total = Counter(
    "self_healing_remediation_events_total",
    "Total de eventos de remediação",
    ["incident_type", "playbook_id", "outcome"],
)

remediation_duration_seconds = Histogram(
    "self_healing_remediation_duration_seconds",
    "Tempo para completar remediação",
    ["incident_type", "playbook_id"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0],
)

remediation_success_rate = Gauge(
    "self_healing_remediation_success_rate", "Taxa de sucesso de remediação", ["incident_type"]
)

# Métricas de MTTR (Mean Time To Recover)
mt_seconds = Histogram(
    "self_healing_mttr_seconds",
    "Mean Time To Recover - tempo médio para recuperação",
    ["incident_type", "severity"],
    buckets=[60.0, 300.0, 600.0, 1800.0, 3600.0, 7200.0, 86400.0],
)

mttr_by_type = Gauge(
    "self_healing_mttr_seconds_current",
    "MTTR atual por tipo de incidente (segundos)",
    ["incident_type", "severity"],
)

# Métricas de Circuit Breaker
circuit_breaker_state = Gauge(
    "self_healing_circuit_breaker_state",
    "Estado do circuit breaker (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["service_name"],
)

circuit_breaker_failures_total = Counter(
    "self_healing_circuit_breaker_failures_total",
    "Total de falhas registradas pelo circuit breaker",
    ["service_name"],
)

circuit_breaker_success_total = Counter(
    "self_healing_circuit_breaker_success_total",
    "Total de sucessos registrados pelo circuit breaker",
    ["service_name"],
)

circuit_breaker_rejected_total = Counter(
    "self_healing_circuit_breaker_rejected_total",
    "Total de requisições rejeitadas pelo circuit breaker",
    ["service_name"],
)

# Métricas de Health Check
health_check_total = Counter(
    "self_healing_health_check_total",
    "Total de health checks executados",
    ["service_name", "outcome"],
)

health_check_duration_seconds = Histogram(
    "self_healing_health_check_duration_seconds",
    "Duração do health check",
    ["service_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
)

service_health_status = Gauge(
    "self_healing_service_health_status",
    "Status de saúde do serviço (1=saudável, 0=não saudável)",
    ["service_name"],
)

# Métricas de Kafka Lag
kafka_consumer_lag = Gauge(
    "self_healing_kafka_consumer_lag",
    "Lag do consumidor Kafka",
    ["consumer_group", "topic", "partition"],
)

kafka_consumer_lag_total = Gauge(
    "self_healing_kafka_consumer_lag_total",
    "Lag total do consumidor Kafka",
    ["consumer_group", "topic"],
)

# Métricas de Playbook
playbook_execution_total = Counter(
    "self_healing_playbook_execution_total",
    "Total de execuções de playbook",
    ["playbook_id", "outcome"],
)

playbook_execution_duration_seconds = Histogram(
    "self_healing_playbook_execution_duration_seconds",
    "Duração da execução do playbook",
    ["playbook_id"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
)

playbook_step_execution_total = Counter(
    "self_healing_playbook_step_execution_total",
    "Total de execuções de steps de playbook",
    ["playbook_id", "step_name", "outcome"],
)

# Métricas de Informação
build_info = Info("self_healing_build_info", "Informações de build do Self-Healing Engine")


# Classe para rastrear MTTR
class MTTRTracker:
    """
    Rastreia Mean Time To Recover para incidentes.

    Calcula o tempo médio entre detecção e resolução de incidentes.
    """

    def __init__(self):
        self._incident_start_times: Dict[str, datetime] = {}
        self._incident_resolutions: list[tuple[str, str, str, timedelta]] = []

    def start_tracking(self, incident_id: str, incident_type: str, severity: str):
        """Inicia rastreamento de incidente."""
        key = f"{incident_type}:{severity}:{incident_id}"
        self._incident_start_times[key] = datetime.now(timezone.utc)
        active_incidents.labels(incident_type=incident_type, severity=severity).inc()

    def end_tracking(self, incident_id: str, incident_type: str, severity: str) -> float:
        """
        Finaliza rastreamento e retorna MTTR em segundos.

        Returns:
            MTTR em segundos
        """
        key = f"{incident_type}:{severity}:{incident_id}"
        start_time = self._incident_start_times.get(key)

        if start_time:
            duration = datetime.now(timezone.utc) - start_time
            duration_seconds = duration.total_seconds()

            # Registra no histograma
            mt_seconds.labels(incident_type=incident_type, severity=severity).observe(
                duration_seconds
            )

            # Atualiza gauge
            mttr_by_type.labels(incident_type=incident_type, severity=severity).set(
                duration_seconds
            )

            # Decrementa incidentes ativos
            active_incidents.labels(incident_type=incident_type, severity=severity).dec()

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


def record_detection(incident_type: str, severity: str, detected_by: str, duration_seconds: float):
    """Registra um evento de detecção."""
    detection_events_total.labels(
        incident_type=incident_type, severity=severity, detected_by=detected_by
    ).inc()
    detection_duration_seconds.labels(incident_type=incident_type).observe(duration_seconds)


def record_remediation(incident_type: str, playbook_id: str, outcome: str, duration_seconds: float):
    """Registra um evento de remediação."""
    remediation_events_total.labels(
        incident_type=incident_type, playbook_id=playbook_id, outcome=outcome
    ).inc()
    remediation_duration_seconds.labels(
        incident_type=incident_type, playbook_id=playbook_id
    ).observe(duration_seconds)


def record_circuit_breaker_state(service_name: str, state: str):  # "CLOSED", "OPEN", "HALF_OPEN"
    """Registra mudança de estado do circuit breaker."""
    state_map = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}
    circuit_breaker_state.labels(service_name=service_name).set(state_map.get(state, 0))


def record_health_check(
    service_name: str,
    outcome: str,  # "success", "failure"
    duration_seconds: float,
    is_healthy: bool,
):
    """Registra resultado de health check."""
    health_check_total.labels(service_name=service_name, outcome=outcome).inc()
    health_check_duration_seconds.labels(service_name=service_name).observe(duration_seconds)
    service_health_status.labels(service_name=service_name).set(1 if is_healthy else 0)


def record_kafka_lag(consumer_group: str, topic: str, partition: int, lag: int):
    """Registra lag de consumidor Kafka."""
    kafka_consumer_lag.labels(consumer_group=consumer_group, topic=topic, partition=partition).set(
        lag
    )


def record_kafka_lag_total(consumer_group: str, topic: str, total_lag: int):
    """Registra lag total de consumidor Kafka."""
    kafka_consumer_lag_total.labels(consumer_group=consumer_group, topic=topic).set(total_lag)


def set_build_info(version: str, commit: str, build_date: str):
    """Define informações de build."""
    build_info.info({"version": version, "commit": commit, "build_date": build_date})


def get_metrics_text() -> str:
    """
    Retorna todas as métricas em formato Prometheus text.

    Returns:
        String com métricas no formato Prometheus
    """
    from prometheus_client import generate_latest

    return generate_latest(REGISTRY).decode("utf-8")
