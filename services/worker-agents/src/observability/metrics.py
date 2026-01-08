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

        self.kafka_producer_initialized_total = Counter(
            'worker_agent_kafka_producer_initialized_total',
            'Total de inicializações do producer Kafka'
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

        # Build
        self.build_tasks_executed_total = Counter(
            'worker_agent_build_tasks_executed_total',
            'Total de tarefas BUILD executadas',
            ['status']
        )
        self.build_duration_seconds = Histogram(
            'worker_agent_build_duration_seconds',
            'Tempo de execução de etapas de build',
            ['stage'],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600, 14400]
        )
        self.build_artifacts_generated_total = Counter(
            'worker_agent_build_artifacts_generated_total',
            'Total de artefatos gerados em builds',
            ['type']
        )
        self.code_forge_api_calls_total = Counter(
            'worker_agent_code_forge_api_calls_total',
            'Total de chamadas à API CodeForge',
            ['method', 'status']
        )

        # Deploy
        self.deploy_tasks_executed_total = Counter(
            'worker_agent_deploy_tasks_executed_total',
            'Total de tarefas DEPLOY executadas',
            ['status']
        )
        self.deploy_duration_seconds = Histogram(
            'worker_agent_deploy_duration_seconds',
            'Tempo de execução de deploy por etapa',
            ['stage'],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600, 900, 1800]
        )
        self.argocd_api_calls_total = Counter(
            'worker_agent_argocd_api_calls_total',
            'Total de chamadas à API do ArgoCD',
            ['method', 'status']
        )
        self.deploy_rollbacks_total = Counter(
            'worker_agent_deploy_rollbacks_total',
            'Total de rollbacks executados',
            ['reason']
        )

        # Test
        self.test_tasks_executed_total = Counter(
            'worker_agent_test_tasks_executed_total',
            'Total de tarefas TEST executadas',
            ['status', 'suite']
        )
        self.test_duration_seconds = Histogram(
            'worker_agent_test_duration_seconds',
            'Tempo de execução dos testes',
            ['suite'],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600]
        )
        self.tests_passed_total = Counter(
            'worker_agent_tests_passed_total',
            'Total de testes aprovados',
            ['suite']
        )
        self.tests_failed_total = Counter(
            'worker_agent_tests_failed_total',
            'Total de testes reprovados',
            ['suite']
        )
        self.test_coverage_percent = Gauge(
            'worker_agent_test_coverage_percent',
            'Cobertura percentual por suíte de teste',
            ['suite']
        )
        self.github_actions_api_calls_total = Counter(
            'worker_agent_github_actions_api_calls_total',
            'Total de chamadas à API do GitHub Actions',
            ['method', 'status']
        )

        # Validate
        self.validate_tasks_executed_total = Counter(
            'worker_agent_validate_tasks_executed_total',
            'Total de tarefas VALIDATE executadas',
            ['status', 'tool']
        )
        self.validate_duration_seconds = Histogram(
            'worker_agent_validate_duration_seconds',
            'Tempo de execução das validações',
            ['tool'],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600]
        )
        self.validate_violations_total = Counter(
            'worker_agent_validate_violations_total',
            'Total de violações encontradas',
            ['severity', 'tool']
        )
        self.validate_tools_executed_total = Counter(
            'worker_agent_validate_tools_executed_total',
            'Total de execuções de ferramentas de validação',
            ['tool', 'status']
        )

        # Execute
        self.execute_tasks_executed_total = Counter(
            'worker_agent_execute_tasks_executed_total',
            'Total de tarefas EXECUTE executadas',
            ['status']
        )

        # Discovery
        self.discovery_requests_total = Counter(
            'worker_agent_discovery_requests_total',
            'Total de requisicoes de descoberta de agentes',
            ['status']
        )

        self.discovery_agents_found = Histogram(
            'worker_agent_discovery_agents_found',
            'Numero de agentes encontrados por descoberta',
            buckets=[0, 1, 2, 3, 5, 10, 20, 50]
        )

        self.discovery_duration_seconds = Histogram(
            'worker_agent_discovery_duration_seconds',
            'Duracao de requisicoes de descoberta',
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
        )

        logger.info('worker_agent_metrics_initialized')


def init_metrics(config):
    '''Inicializar métricas'''
    return WorkerAgentMetrics(config)
