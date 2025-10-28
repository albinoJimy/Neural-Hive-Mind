"""
Temporal Worker para executar workflows e activities.
"""
from temporalio.client import Client
from temporalio.worker import Worker
import structlog

logger = structlog.get_logger()


class TemporalWorkerManager:
    """Gerencia o Temporal Worker."""

    def __init__(self, config, temporal_client: Client, kafka_producer=None, mongodb_client=None, registry_client=None):
        """
        Inicializa o worker manager.

        Args:
            config: Configurações da aplicação
            temporal_client: Cliente Temporal
            kafka_producer: Cliente Kafka Producer (opcional)
            mongodb_client: Cliente MongoDB (opcional)
            registry_client: Cliente do Service Registry (opcional)
        """
        self.config = config
        self.temporal_client = temporal_client
        self.kafka_producer = kafka_producer
        self.mongodb_client = mongodb_client
        self.registry_client = registry_client
        self.worker = None
        self.running = False

    async def initialize(self):
        """Inicializa o Temporal Worker."""
        logger.info('Inicializando Temporal Worker', task_queue=self.config.temporal_task_queue)

        # Import workflows e activities
        from src.workflows.orchestration_workflow import OrchestrationWorkflow
        from src.activities.plan_validation import (
            validate_cognitive_plan,
            audit_validation,
            optimize_dag
        )
        from src.activities.ticket_generation import (
            generate_execution_tickets,
            allocate_resources,
            publish_ticket_to_kafka,
            set_activity_dependencies
        )
        from src.activities.result_consolidation import (
            consolidate_results,
            trigger_self_healing,
            publish_telemetry,
            buffer_telemetry
        )

        # Injetar dependências nas activities
        if self.kafka_producer and self.mongodb_client:
            set_activity_dependencies(
                self.kafka_producer,
                self.mongodb_client,
                self.registry_client
            )
            logger.info(
                'Dependências injetadas nas activities',
                registry_enabled=self.registry_client is not None
            )
        else:
            logger.warning('Kafka Producer ou MongoDB Client não fornecidos - activities podem falhar')

        # Criar Worker
        self.worker = Worker(
            self.temporal_client,
            task_queue=self.config.temporal_task_queue,
            workflows=[OrchestrationWorkflow],
            activities=[
                validate_cognitive_plan,
                audit_validation,
                optimize_dag,
                generate_execution_tickets,
                allocate_resources,
                publish_ticket_to_kafka,
                consolidate_results,
                trigger_self_healing,
                publish_telemetry,
                buffer_telemetry
            ],
            max_concurrent_workflow_tasks=10,
            max_concurrent_activities=50
        )

        logger.info('Temporal Worker inicializado com sucesso')

    async def start(self):
        """Inicia o worker."""
        if not self.worker:
            raise RuntimeError('Worker não foi inicializado. Chame initialize() primeiro.')

        logger.info('Iniciando Temporal Worker')
        self.running = True

        await self.worker.run()

    async def stop(self):
        """Para o worker gracefully."""
        logger.info('Parando Temporal Worker')
        self.running = False
        # Temporal SDK gerencia shutdown automaticamente


async def create_temporal_client(config) -> Client:
    """
    Cria cliente Temporal.

    Args:
        config: Configurações da aplicação

    Returns:
        Cliente Temporal conectado
    """
    logger.info('Conectando ao Temporal Server', host=config.temporal_host, port=config.temporal_port)

    try:
        client = await Client.connect(
            f'{config.temporal_host}:{config.temporal_port}',
            namespace=config.temporal_namespace,
            # tls=config.temporal_tls_enabled  # Configurar TLS para produção
        )

        logger.info('Cliente Temporal criado com sucesso')
        return client

    except Exception as e:
        logger.error('Erro ao conectar ao Temporal Server', error=str(e), exc_info=True)
        raise
