from prometheus_client import Counter, Gauge, Histogram
import structlog

logger = structlog.get_logger()


class WorkerAgentMetrics:
    '''Métricas Prometheus para Worker Agents'''

    def __init__(self, config):
        self.config = config

        # Lifecycle
        self.startup_total = Counter(
            'worker_agent_startup_total',
            'Total de inicializações do Worker Agent'
        )

        self.registered_total = Counter(
            'worker_agent_registered_total',
            'Total de registros no Service Registry'
        )

        self.heartbeat_total = Counter(
            'worker_agent_heartbeat_total',
            'Total de heartbeats enviados',
            ['status']
        )

        self.deregistered_total = Counter(
            'worker_agent_deregistered_total',
            'Total de deregistros do Service Registry'
        )

        # Tickets
        self.tickets_consumed_total = Counter(
            'worker_agent_tickets_consumed_total',
            'Total de tickets consumidos do Kafka',
            ['task_type']
        )

        self.tickets_processing_total = Counter(
            'worker_agent_tickets_processing_total',
            'Total de tickets em processamento',
            ['task_type']
        )

        self.tickets_completed_total = Counter(
            'worker_agent_tickets_completed_total',
            'Total de tickets concluídos com sucesso',
            ['task_type']
        )

        self.tickets_failed_total = Counter(
            'worker_agent_tickets_failed_total',
            'Total de tickets falhados',
            ['task_type', 'error_type']
        )

        self.active_tasks = Gauge(
            'worker_agent_active_tasks',
            'Número de tarefas ativas no momento'
        )

        self.task_duration_seconds = Histogram(
            'worker_agent_task_duration_seconds',
            'Duração de execução de tarefas',
            ['task_type'],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600]
        )

        # Dependencies
        self.dependency_checks_total = Counter(
            'worker_agent_dependency_checks_total',
            'Total de verificações de dependências',
            ['result']
        )

        self.dependency_wait_duration_seconds = Histogram(
            'worker_agent_dependency_wait_duration_seconds',
            'Tempo de espera por dependências',
            buckets=[1, 5, 10, 30, 60, 120, 300]
        )

        # Retries
        self.task_retries_total = Counter(
            'worker_agent_task_retries_total',
            'Total de tentativas de retry',
            ['task_type', 'attempt']
        )

        self.tasks_cancelled_total = Counter(
            'worker_agent_tasks_cancelled_total',
            'Total de tarefas canceladas'
        )

        # API Calls
        self.ticket_api_calls_total = Counter(
            'worker_agent_ticket_api_calls_total',
            'Total de chamadas ao Execution Ticket Service',
            ['method', 'status']
        )

        self.ticket_status_updates_total = Counter(
            'worker_agent_ticket_status_updates_total',
            'Total de atualizações de status',
            ['status']
        )

        self.ticket_tokens_obtained_total = Counter(
            'worker_agent_ticket_tokens_obtained_total',
            'Total de tokens JWT obtidos'
        )

        # Kafka
        self.kafka_consumer_initialized_total = Counter(
            'worker_agent_kafka_consumer_initialized_total',
            'Total de inicializações do consumer Kafka'
        )

        self.kafka_consumer_errors_total = Counter(
            'worker_agent_kafka_consumer_errors_total',
            'Total de erros no consumer Kafka',
            ['error_type']
        )

        self.results_published_total = Counter(
            'worker_agent_results_published_total',
            'Total de resultados publicados',
            ['status']
        )

        self.kafka_producer_errors_total = Counter(
            'worker_agent_kafka_producer_errors_total',
            'Total de erros no producer Kafka'
        )

        # Executors
        self.executors_registered_total = Counter(
            'worker_agent_executors_registered_total',
            'Total de executores registrados',
            ['task_type']
        )

        self.build_tasks_executed_total = Counter(
            'worker_agent_build_tasks_executed_total',
            'Total de tarefas BUILD executadas'
        )

        self.deploy_tasks_executed_total = Counter(
            'worker_agent_deploy_tasks_executed_total',
            'Total de tarefas DEPLOY executadas'
        )

        self.test_tasks_executed_total = Counter(
            'worker_agent_test_tasks_executed_total',
            'Total de tarefas TEST executadas'
        )

        self.validate_tasks_executed_total = Counter(
            'worker_agent_validate_tasks_executed_total',
            'Total de tarefas VALIDATE executadas'
        )

        self.execute_tasks_executed_total = Counter(
            'worker_agent_execute_tasks_executed_total',
            'Total de tarefas EXECUTE executadas'
        )

        logger.info('worker_agent_metrics_initialized')


def init_metrics(config):
    '''Inicializar métricas'''
    return WorkerAgentMetrics(config)
