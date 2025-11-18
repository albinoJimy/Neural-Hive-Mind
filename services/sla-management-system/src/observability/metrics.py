"""
Métricas Prometheus para SLA Management System.
"""

from prometheus_client import Counter, Gauge, Histogram
from typing import Dict

from ..models.error_budget import ErrorBudget


class SLAMetrics:
    """Métricas Prometheus do SLA Management System."""

    def __init__(self):
        # Cálculos de Budget
        self.calculations_total = Counter(
            "sla_calculations_total",
            "Total de cálculos de budget executados",
            ["slo_id", "service_name", "status"]
        )

        self.calculation_duration = Histogram(
            "sla_calculation_duration_seconds",
            "Duração dos cálculos de budget",
            ["slo_id", "service_name"],
            buckets=[0.1, 0.5, 1, 2, 5, 10]
        )

        # Error Budgets
        self.budget_remaining = Gauge(
            "sla_budget_remaining_percent",
            "Percentual de budget restante",
            ["slo_id", "service_name", "slo_type"]
        )

        self.budget_consumed = Gauge(
            "sla_budget_consumed_percent",
            "Percentual de budget consumido",
            ["slo_id", "service_name", "slo_type"]
        )

        self.budget_status = Gauge(
            "sla_budget_status",
            "Status do budget (0=HEALTHY, 1=WARNING, 2=CRITICAL, 3=EXHAUSTED)",
            ["slo_id", "service_name"]
        )

        self.burn_rate = Gauge(
            "sla_burn_rate",
            "Taxa de consumo do budget",
            ["slo_id", "service_name", "window_hours"]
        )

        # Freezes
        self.freezes_active = Gauge(
            "sla_freezes_active",
            "Número de freezes ativos",
            ["service_name", "scope"]
        )

        self.freezes_activated_total = Counter(
            "sla_freezes_activated_total",
            "Total de freezes acionados",
            ["service_name", "policy_id", "scope"]
        )

        self.freezes_resolved_total = Counter(
            "sla_freezes_resolved_total",
            "Total de freezes resolvidos",
            ["service_name", "policy_id", "scope"]
        )

        self.freeze_duration = Histogram(
            "sla_freeze_duration_seconds",
            "Duração dos freezes",
            ["service_name", "policy_id"],
            buckets=[60, 300, 600, 1800, 3600, 7200]
        )

        # SLOs
        self.slos_total = Gauge(
            "sla_slos_total",
            "Total de SLOs definidos",
            ["slo_type", "enabled"]
        )

        self.slo_violations_total = Counter(
            "sla_slo_violations_total",
            "Total de violações de SLO",
            ["slo_id", "service_name", "severity"]
        )

        # Políticas
        self.policies_total = Gauge(
            "sla_policies_total",
            "Total de políticas definidas",
            ["scope", "enabled"]
        )

        self.policy_evaluations_total = Counter(
            "sla_policy_evaluations_total",
            "Total de avaliações de política",
            ["policy_id", "result"]
        )

        # Integrações
        self.prometheus_queries_total = Counter(
            "sla_prometheus_queries_total",
            "Total de queries ao Prometheus",
            ["query_type", "status"]
        )

        self.prometheus_query_duration = Histogram(
            "sla_prometheus_query_duration_seconds",
            "Duração das queries ao Prometheus",
            ["query_type"],
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30]
        )

        self.alertmanager_webhooks_total = Counter(
            "sla_alertmanager_webhooks_received_total",
            "Total de webhooks recebidos do Alertmanager",
            ["status"]
        )

        self.kafka_events_published_total = Counter(
            "sla_kafka_events_published_total",
            "Total de eventos publicados no Kafka",
            ["topic", "event_type"]
        )

        # Erros de conexão
        self.postgresql_connection_errors_total = Counter(
            "sla_postgresql_connection_errors_total",
            "Total de erros de conexão com PostgreSQL"
        )

        self.redis_connection_errors_total = Counter(
            "sla_redis_connection_errors_total",
            "Total de erros de conexão com Redis"
        )

        # Erros de sincronização de CRD
        self.crd_sync_errors_total = Counter(
            "sla_crd_sync_errors_total",
            "Total de erros ao sincronizar CRDs com PostgreSQL",
            ["crd_type"]
        )

    def record_calculation(
        self,
        slo_id: str,
        service_name: str,
        duration: float,
        success: bool
    ) -> None:
        """Registra execução de cálculo."""
        status = "success" if success else "error"
        self.calculations_total.labels(
            slo_id=slo_id,
            service_name=service_name,
            status=status
        ).inc()

        if success:
            self.calculation_duration.labels(
                slo_id=slo_id,
                service_name=service_name
            ).observe(duration)

    def update_budget_metrics(self, budget: ErrorBudget) -> None:
        """Atualiza métricas de budget."""
        # Inferir slo_type do metadata ou usar "CUSTOM"
        slo_type = budget.metadata.get("slo_type", "CUSTOM")

        self.budget_remaining.labels(
            slo_id=budget.slo_id,
            service_name=budget.service_name,
            slo_type=slo_type
        ).set(budget.error_budget_remaining)

        self.budget_consumed.labels(
            slo_id=budget.slo_id,
            service_name=budget.service_name,
            slo_type=slo_type
        ).set(budget.error_budget_consumed)

        # Status numérico
        status_map = {
            "HEALTHY": 0,
            "WARNING": 1,
            "CRITICAL": 2,
            "EXHAUSTED": 3
        }
        status_value = status_map.get(budget.status.value, 0)

        self.budget_status.labels(
            slo_id=budget.slo_id,
            service_name=budget.service_name
        ).set(status_value)

        # Burn rates
        for burn_rate in budget.burn_rates:
            self.burn_rate.labels(
                slo_id=budget.slo_id,
                service_name=budget.service_name,
                window_hours=str(burn_rate.window_hours)
            ).set(burn_rate.rate)

    def record_freeze_activated(
        self,
        service_name: str,
        policy_id: str,
        scope: str
    ) -> None:
        """Registra freeze acionado."""
        self.freezes_activated_total.labels(
            service_name=service_name,
            policy_id=policy_id,
            scope=scope
        ).inc()

    def record_freeze_resolved(
        self,
        service_name: str,
        policy_id: str,
        scope: str,
        duration: float
    ) -> None:
        """Registra freeze resolvido."""
        self.freezes_resolved_total.labels(
            service_name=service_name,
            policy_id=policy_id,
            scope=scope
        ).inc()

        self.freeze_duration.labels(
            service_name=service_name,
            policy_id=policy_id
        ).observe(duration)

    def update_freeze_active_count(
        self,
        service_name: str,
        scope: str,
        count: int
    ) -> None:
        """Atualiza contador de freezes ativos."""
        self.freezes_active.labels(
            service_name=service_name,
            scope=scope
        ).set(count)

    def record_slo_violation(
        self,
        slo_id: str,
        service_name: str,
        severity: str
    ) -> None:
        """Registra violação de SLO."""
        self.slo_violations_total.labels(
            slo_id=slo_id,
            service_name=service_name,
            severity=severity
        ).inc()

    def record_prometheus_query(
        self,
        query_type: str,
        duration: float,
        success: bool
    ) -> None:
        """Registra query ao Prometheus."""
        status = "success" if success else "error"

        self.prometheus_queries_total.labels(
            query_type=query_type,
            status=status
        ).inc()

        if success:
            self.prometheus_query_duration.labels(
                query_type=query_type
            ).observe(duration)

    def record_webhook_received(self, success: bool) -> None:
        """Registra webhook recebido."""
        status = "processed" if success else "error"
        self.alertmanager_webhooks_total.labels(status=status).inc()

    def record_kafka_event(self, topic: str, event_type: str) -> None:
        """Registra evento publicado no Kafka."""
        self.kafka_events_published_total.labels(
            topic=topic,
            event_type=event_type
        ).inc()

    def record_postgresql_error(self) -> None:
        """Registra erro de conexão com PostgreSQL."""
        self.postgresql_connection_errors_total.inc()

    def record_redis_error(self) -> None:
        """Registra erro de conexão com Redis."""
        self.redis_connection_errors_total.inc()

    def record_crd_sync_error(self, crd_type: str) -> None:
        """Registra erro de sincronização de CRD."""
        self.crd_sync_errors_total.labels(crd_type=crd_type).inc()


# Instância global
sla_metrics = SLAMetrics()
