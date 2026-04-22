"""
Métricas Prometheus para Hypothesis Library.
"""

from prometheus_client import Counter, Gauge, Histogram


class HypothesisMetrics:
    """Métricas Prometheus do Hypothesis Library."""

    def __init__(self):
        # Hipóteses criadas
        self.hypothesis_created_total = Counter(
            "hypothesis_created_total",
            "Total de hipóteses criadas",
            ["priority", "author"],
        )

        # Hipóteses aprovadas
        self.hypothesis_approved_total = Counter(
            "hypothesis_approved_total",
            "Total de hipóteses aprovadas para teste",
            ["priority", "reviewer"],
        )

        # Hipóteses testadas
        self.hypothesis_tested_total = Counter(
            "hypothesis_tested_total",
            "Total de hipóteses que completaram testes",
            ["outcome"],
        )

        # Hipóteses por status atual
        self.hypothesis_status_current = Gauge(
            "hypothesis_status_current",
            "Número de hipóteses por status atual",
            ["status"],
        )

        # Transições de status
        self.hypothesis_transitions_total = Counter(
            "hypothesis_transitions_total",
            "Total de transições de status executadas",
            ["from_status", "to_status", "triggered_by"],
        )

        # Duração no status
        self.hypothesis_status_duration = Histogram(
            "hypothesis_status_duration_seconds",
            "Tempo que hipóteses passaram em cada status",
            ["status"],
            buckets=[3600, 86400, 604800, 2592000, 7776000],  # 1h, 1d, 7d, 30d, 90d
        )

        # Tempo de aprovação
        self.approval_duration = Histogram(
            "hypothesis_approval_duration_seconds",
            "Tempo entre proposta e aprovação",
            ["priority"],
            buckets=[60, 300, 3600, 86400, 604800],  # 1min, 5min, 1h, 1d, 7d
        )

        # Tempo de teste
        self.testing_duration = Histogram(
            "hypothesis_testing_duration_seconds",
            "Duração dos testes de hipótese",
            ["priority"],
            buckets=[3600, 86400, 604800, 2592000],  # 1h, 1d, 7d, 30d
        )

        # Versões criadas
        self.hypothesis_versions_total = Counter(
            "hypothesis_versions_total",
            "Total de versões de hipóteses criadas",
            ["change_type"],
        )

        # Taxa de aceitação/rejeição
        self.hypothesis_outcome_total = Counter(
            "hypothesis_outcome_total",
            "Resultado final das hipóteses",
            ["outcome", "priority"],
        )

        # Experimentos associados
        self.hypothesis_experiments_total = Gauge(
            "hypothesis_experiments_total",
            "Número de experimentos associados a hipóteses",
            ["status"],
        )

        # Erros de workflow
        self.workflow_errors_total = Counter(
            "hypothesis_workflow_errors_total",
            "Total de erros de workflow de hipóteses",
            ["error_type", "from_status", "to_status"],
        )

        # Hipóteses por prioridade
        self.hypothesis_by_priority = Gauge(
            "hypothesis_by_priority",
            "Número de hipóteses por prioridade",
            ["priority", "status"],
        )

        # Hipóteses arquivadas
        self.hypothesis_archived_total = Counter(
            "hypothesis_archived_total",
            "Total de hipóteses arquivadas",
            ["previous_status"],
        )

    def record_hypothesis_created(self, priority: str, author: str) -> None:
        """Registra criação de hipótese.

        Args:
            priority: Prioridade da hipótese
            author: Autor da hipótese
        """
        self.hypothesis_created_total.labels(priority=priority, author=author).inc()

    def record_hypothesis_approved(self, priority: str, reviewer: str) -> None:
        """Registra aprovação de hipótese.

        Args:
            priority: Prioridade da hipótese
            reviewer: Revisor que aprovou
        """
        self.hypothesis_approved_total.labels(priority=priority, reviewer=reviewer).inc()

    def record_hypothesis_tested(self, outcome: str) -> None:
        """Registra hipótese testada.

        Args:
            outcome: Resultado do teste (positive, negative, inconclusive)
        """
        self.hypothesis_tested_total.labels(outcome=outcome).inc()

    def update_status_count(self, status: str, count: int) -> None:
        """Atualiza contador de hipóteses por status.

        Args:
            status: Status da hipótese
            count: Quantidade
        """
        self.hypothesis_status_current.labels(status=status).set(count)

    def record_transition(self, from_status: str, to_status: str, triggered_by: str) -> None:
        """Registra transição de status.

        Args:
            from_status: Status anterior
            to_status: Novo status
            triggered_by: Quem triggerou a transição
        """
        self.hypothesis_transitions_total.labels(
            from_status=from_status, to_status=to_status, triggered_by=triggered_by
        ).inc()

    def record_approval_duration(self, priority: str, duration: float) -> None:
        """Registra duração da aprovação.

        Args:
            priority: Prioridade da hipótese
            duration: Duração em segundos
        """
        self.approval_duration.labels(priority=priority).observe(duration)

    def record_testing_duration(self, priority: str, duration: float) -> None:
        """Registra duração do teste.

        Args:
            priority: Prioridade da hipótese
            duration: Duração em segundos
        """
        self.testing_duration.labels(priority=priority).observe(duration)

    def record_status_duration(self, status: str, duration: float) -> None:
        """Registra duração em um status.

        Args:
            status: Status
            duration: Duração em segundos
        """
        self.hypothesis_status_duration.labels(status=status).observe(duration)

    def record_version_created(self, change_type: str) -> None:
        """Registra criação de versão.

        Args:
            change_type: Tipo de mudança (create, update, status_change)
        """
        self.hypothesis_versions_total.labels(change_type=change_type).inc()

    def record_outcome(self, outcome: str, priority: str) -> None:
        """Registra resultado final.

        Args:
            outcome: Resultado (accepted, rejected, archived)
            priority: Prioridade da hipótese
        """
        self.hypothesis_outcome_total.labels(outcome=outcome, priority=priority).inc()

    def update_experiment_count(self, status: str, count: int) -> None:
        """Atualiza contador de experimentos.

        Args:
            status: Status das hipóteses com experimentos
            count: Quantidade
        """
        self.hypothesis_experiments_total.labels(status=status).set(count)

    def record_workflow_error(self, error_type: str, from_status: str, to_status: str) -> None:
        """Registra erro de workflow.

        Args:
            error_type: Tipo do erro (invalid_transition, not_found, etc)
            from_status: Status de origem
            to_status: Status de destino
        """
        self.workflow_errors_total.labels(
            error_type=error_type, from_status=from_status, to_status=to_status
        ).inc()

    def update_priority_count(self, priority: str, status: str, count: int) -> None:
        """Atualiza contador por prioridade.

        Args:
            priority: Prioridade
            status: Status
            count: Quantidade
        """
        self.hypothesis_by_priority.labels(priority=priority, status=status).set(count)

    def record_archived(self, previous_status: str) -> None:
        """Registra arquivamento.

        Args:
            previous_status: Status anterior ao arquivamento
        """
        self.hypothesis_archived_total.labels(previous_status=previous_status).inc()


# Instância global
hypothesis_metrics = HypothesisMetrics()
