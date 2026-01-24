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

        self.tickets_in_flight = Gauge(
            'worker_agent_tickets_in_flight',
            'Número de tickets consumidos mas ainda não finalizados (backpressure)'
        )

        self.max_concurrent_tickets = Gauge(
            'worker_agent_max_concurrent_tickets',
            'Limite máximo configurado de tickets em processamento simultâneo'
        )
        # Inicializar com valor da config
        max_tickets = getattr(config, 'max_concurrent_tickets', 10)
        self.max_concurrent_tickets.set(max_tickets)

        self.consumer_paused_total = Counter(
            'worker_agent_consumer_paused_total',
            'Total de vezes que o consumer foi pausado por backpressure'
        )

        self.consumer_resumed_total = Counter(
            'worker_agent_consumer_resumed_total',
            'Total de vezes que o consumer foi resumido após backpressure'
        )

        self.consumer_pause_duration_seconds = Histogram(
            'worker_agent_consumer_pause_duration_seconds',
            'Duração de pausas do consumer por backpressure',
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300]
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

        # Idempotency
        self.duplicates_detected_total = Counter(
            'worker_agent_duplicates_detected_total',
            'Total de tickets duplicados detectados',
            ['component']
        )

        self.idempotency_cache_hits_total = Counter(
            'worker_agent_idempotency_cache_hits_total',
            'Total de cache hits na verificação de idempotência'
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

        # Dead Letter Queue (DLQ)
        self.dlq_messages_total = Counter(
            'worker_agent_dlq_messages_total',
            'Total de mensagens enviadas para DLQ',
            ['reason', 'task_type']
        )

        self.dlq_publish_duration_seconds = Histogram(
            'worker_agent_dlq_publish_duration_seconds',
            'Duracao de publicacao no DLQ',
            buckets=[0.1, 0.5, 1, 2, 5, 10]
        )

        self.dlq_publish_errors_total = Counter(
            'worker_agent_dlq_publish_errors_total',
            'Total de erros ao publicar no DLQ',
            ['error_type']
        )

        self.ticket_retry_count = Histogram(
            'worker_agent_ticket_retry_count',
            'Numero de tentativas de processamento por ticket',
            ['task_type'],
            buckets=[1, 2, 3, 4, 5, 10, 20]
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
        self.flux_api_calls_total = Counter(
            'worker_agent_flux_api_calls_total',
            'Total de chamadas a API do Flux',
            ['method', 'status']
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

        # GitLab CI metrics
        self.gitlab_ci_api_calls_total = Counter(
            'worker_agent_gitlab_ci_api_calls_total',
            'Total de chamadas à API do GitLab CI',
            ['method', 'status']
        )

        # Jenkins metrics
        self.jenkins_api_calls_total = Counter(
            'worker_agent_jenkins_api_calls_total',
            'Total de chamadas à API do Jenkins',
            ['method', 'status']
        )

        # Test report parsing metrics
        self.test_report_parsing_total = Counter(
            'worker_agent_test_report_parsing_total',
            'Total de parsing de relatorios de teste',
            ['format', 'status']
        )

        self.coverage_report_parsing_total = Counter(
            'worker_agent_coverage_report_parsing_total',
            'Total de parsing de relatorios de coverage',
            ['format', 'status']
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

        # OPA
        self.opa_api_calls_total = Counter(
            'worker_agent_opa_api_calls_total',
            'Total de chamadas à API OPA',
            ['method', 'status']
        )
        self.policy_violations_total = Counter(
            'policy_violations_total',
            'Total de violacoes de politica detectadas',
            ['severity', 'tool']
        )
        self.opa_policy_evaluation_duration_seconds = Histogram(
            'worker_agent_opa_policy_evaluation_duration_seconds',
            'Duração de avaliações de política OPA',
            ['policy_path'],
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30]
        )
        self.opa_bundle_activation_duration_seconds = Histogram(
            'worker_agent_opa_bundle_activation_duration_seconds',
            'Duração de ativação de bundles OPA',
            ['bundle_name'],
            buckets=[1, 5, 10, 30, 60, 120]
        )

        # Execute
        self.execute_tasks_executed_total = Counter(
            'worker_agent_execute_tasks_executed_total',
            'Total de tarefas EXECUTE executadas',
            ['status']
        )

        self.execute_duration_seconds = Histogram(
            'worker_agent_execute_duration_seconds',
            'Duração de execução de tarefas EXECUTE por runtime',
            ['runtime'],
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600]
        )

        self.execute_runtime_fallbacks_total = Counter(
            'worker_agent_execute_runtime_fallbacks_total',
            'Total de fallbacks entre runtimes de execução',
            ['from_runtime', 'to_runtime']
        )

        # Docker Runtime
        self.docker_executions_total = Counter(
            'worker_agent_docker_executions_total',
            'Total de execuções Docker',
            ['status']
        )

        self.docker_execution_duration_seconds = Histogram(
            'worker_agent_docker_execution_duration_seconds',
            'Duração de execuções Docker',
            ['stage'],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600]
        )

        self.docker_api_calls_total = Counter(
            'worker_agent_docker_api_calls_total',
            'Total de chamadas à API Docker',
            ['method', 'status']
        )

        # Kubernetes Jobs Runtime
        self.k8s_jobs_executed_total = Counter(
            'worker_agent_k8s_jobs_executed_total',
            'Total de Jobs K8s executados',
            ['status']
        )

        self.k8s_job_duration_seconds = Histogram(
            'worker_agent_k8s_job_duration_seconds',
            'Duração de execução de Jobs K8s',
            ['stage'],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600]
        )

        self.k8s_api_calls_total = Counter(
            'worker_agent_k8s_api_calls_total',
            'Total de chamadas à API Kubernetes',
            ['method', 'status']
        )

        # Lambda Runtime
        self.lambda_invocations_total = Counter(
            'worker_agent_lambda_invocations_total',
            'Total de invocações Lambda',
            ['status']
        )

        self.lambda_duration_seconds = Histogram(
            'worker_agent_lambda_duration_seconds',
            'Duração de invocações Lambda',
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600, 900]
        )

        self.lambda_billed_duration_seconds = Histogram(
            'worker_agent_lambda_billed_duration_seconds',
            'Duração faturada de invocações Lambda',
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600, 900]
        )

        # Local Runtime
        self.local_executions_total = Counter(
            'worker_agent_local_executions_total',
            'Total de execuções locais',
            ['status']
        )

        self.local_execution_duration_seconds = Histogram(
            'worker_agent_local_execution_duration_seconds',
            'Duração de execuções locais',
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300]
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
