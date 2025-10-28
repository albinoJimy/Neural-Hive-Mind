"""
Métricas Prometheus customizadas para o Orchestrator Dynamic.
"""
from functools import lru_cache

from prometheus_client import Counter, Histogram, Gauge
import structlog

logger = structlog.get_logger()


class OrchestratorMetrics:
    """Métricas Prometheus do Orchestrator Dynamic."""

    def __init__(self, service_name: str = 'orchestrator-dynamic', component: str = 'orchestration', layer: str = 'orchestration'):
        """
        Inicializa métricas Prometheus.

        Args:
            service_name: Nome do serviço
            component: Nome do componente
            layer: Camada da arquitetura
        """
        self.service_name = service_name
        self.component = component
        self.layer = layer

        # Métricas de Workflows
        self.workflows_started_total = Counter(
            'orchestration_workflows_started_total',
            'Total de workflows iniciados',
            ['status', 'risk_band']
        )

        self.workflows_completed_total = Counter(
            'orchestration_workflows_completed_total',
            'Total de workflows concluídos',
            ['status', 'risk_band']
        )

        self.workflow_duration_seconds = Histogram(
            'orchestration_workflow_duration_seconds',
            'Duração de workflows em segundos',
            ['status', 'risk_band'],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600, 7200, 14400]
        )

        self.workflows_active = Gauge(
            'orchestration_workflows_active',
            'Workflows ativos no momento'
        )

        # Métricas de Tickets
        self.tickets_generated_total = Counter(
            'orchestration_tickets_generated_total',
            'Total de tickets gerados',
            ['task_type', 'risk_band', 'priority']
        )

        self.tickets_published_total = Counter(
            'orchestration_tickets_published_total',
            'Total de tickets publicados no Kafka',
            ['status']
        )

        self.tickets_completed_total = Counter(
            'orchestration_tickets_completed_total',
            'Total de tickets concluídos',
            ['status', 'task_type']
        )

        self.ticket_generation_duration_seconds = Histogram(
            'orchestration_ticket_generation_duration_seconds',
            'Tempo de geração de tickets',
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10]
        )

        # Métricas de SLA
        self.sla_violations_total = Counter(
            'orchestration_sla_violations_total',
            'Total de violações de SLA',
            ['risk_band', 'task_type']
        )

        self.sla_remaining_seconds = Gauge(
            'orchestration_sla_remaining_seconds',
            'Tempo restante de SLA em segundos',
            ['workflow_id', 'risk_band']
        )

        self.deadline_approaching_total = Counter(
            'orchestration_deadline_approaching_total',
            'Workflows próximos do deadline (>80% consumido)'
        )

        # Métricas de Retry e Compensação
        self.retries_total = Counter(
            'orchestration_retries_total',
            'Total de retries',
            ['task_type', 'retry_attempt']
        )

        self.compensations_triggered_total = Counter(
            'orchestration_compensations_triggered_total',
            'Total de compensações acionadas',
            ['reason']
        )

        # Métricas de Kafka
        self.kafka_messages_consumed_total = Counter(
            'orchestration_kafka_messages_consumed_total',
            'Total de mensagens consumidas de plans.consensus'
        )

        self.kafka_messages_produced_total = Counter(
            'orchestration_kafka_messages_produced_total',
            'Total de mensagens produzidas em execution.tickets'
        )

        self.kafka_consumer_lag = Gauge(
            'orchestration_kafka_consumer_lag',
            'Lag do consumer Kafka'
        )

        self.kafka_errors_total = Counter(
            'orchestration_kafka_errors_total',
            'Total de erros Kafka',
            ['operation', 'error_type']
        )

        # Métricas de Validação
        self.plan_validations_total = Counter(
            'orchestration_plan_validations_total',
            'Total de validações de planos',
            ['result']
        )

        self.dag_optimizations_total = Counter(
            'orchestration_dag_optimizations_total',
            'Total de otimizações de DAG'
        )

        # Métricas de Recursos
        self.resource_allocations_total = Counter(
            'orchestration_resource_allocations_total',
            'Total de alocações de recursos',
            ['status']
        )

        self.burst_capacity_activations_total = Counter(
            'orchestration_burst_capacity_activations_total',
            'Total de ativações de burst capacity'
        )

        logger.info('Métricas Prometheus inicializadas', service=service_name, component=component)

    # Métodos helper para registrar métricas

    def record_workflow_started(self, risk_band: str, status: str = 'started'):
        """Registra início de workflow."""
        self.workflows_started_total.labels(status=status, risk_band=risk_band).inc()
        self.workflows_active.inc()

    def record_workflow_completed(self, status: str, risk_band: str, duration_seconds: float):
        """Registra conclusão de workflow."""
        self.workflows_completed_total.labels(status=status, risk_band=risk_band).inc()
        self.workflow_duration_seconds.labels(status=status, risk_band=risk_band).observe(duration_seconds)
        self.workflows_active.dec()

    def record_ticket_generated(self, task_type: str, risk_band: str, priority: str):
        """Registra geração de ticket."""
        self.tickets_generated_total.labels(
            task_type=task_type,
            risk_band=risk_band,
            priority=priority
        ).inc()

    def record_ticket_published(self, status: str = 'published'):
        """Registra publicação de ticket no Kafka."""
        self.tickets_published_total.labels(status=status).inc()

    def record_ticket_completed(self, status: str, task_type: str):
        """Registra conclusão de ticket."""
        self.tickets_completed_total.labels(status=status, task_type=task_type).inc()

    def record_sla_violation(self, risk_band: str, task_type: str):
        """Registra violação de SLA."""
        self.sla_violations_total.labels(risk_band=risk_band, task_type=task_type).inc()

    def update_sla_remaining(self, workflow_id: str, risk_band: str, seconds: float):
        """Atualiza gauge de SLA restante."""
        self.sla_remaining_seconds.labels(workflow_id=workflow_id, risk_band=risk_band).set(seconds)

    def record_deadline_approaching(self):
        """Registra deadline próximo."""
        self.deadline_approaching_total.inc()

    def record_retry(self, task_type: str, attempt: int):
        """Registra retry de tarefa."""
        self.retries_total.labels(task_type=task_type, retry_attempt=str(attempt)).inc()

    def record_compensation(self, reason: str):
        """Registra compensação acionada."""
        self.compensations_triggered_total.labels(reason=reason).inc()

    def record_kafka_message_consumed(self):
        """Registra mensagem consumida do Kafka."""
        self.kafka_messages_consumed_total.inc()

    def record_kafka_message_produced(self):
        """Registra mensagem produzida no Kafka."""
        self.kafka_messages_produced_total.inc()

    def update_kafka_consumer_lag(self, lag: int):
        """Atualiza lag do consumer Kafka."""
        self.kafka_consumer_lag.set(lag)

    def record_kafka_error(self, operation: str, error_type: str):
        """Registra erro Kafka."""
        self.kafka_errors_total.labels(operation=operation, error_type=error_type).inc()

    def record_plan_validation(self, result: str):
        """Registra validação de plano."""
        self.plan_validations_total.labels(result=result).inc()

    def record_dag_optimization(self):
        """Registra otimização de DAG."""
        self.dag_optimizations_total.inc()

    def record_resource_allocation(self, status: str):
        """Registra alocação de recurso."""
        self.resource_allocations_total.labels(status=status).inc()

    def record_burst_capacity_activation(self):
        """Registra ativação de burst capacity."""
        self.burst_capacity_activations_total.inc()


@lru_cache()
def get_metrics() -> OrchestratorMetrics:
    """
    Retorna instância singleton das métricas.

    Returns:
        Instância de OrchestratorMetrics
    """
    return OrchestratorMetrics()
