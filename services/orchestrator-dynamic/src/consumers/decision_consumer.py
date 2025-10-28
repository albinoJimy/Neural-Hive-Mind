"""
Kafka consumer para tópico plans.consensus.
Consome decisões consolidadas e inicia workflows Temporal.
"""
import json
from typing import Optional

from aiokafka import AIOKafkaConsumer
from temporalio.client import Client
import structlog

from src.workflows.orchestration_workflow import OrchestrationWorkflow

logger = structlog.get_logger()


class DecisionConsumer:
    """Consumer Kafka para decisões consolidadas."""

    def __init__(self, config, temporal_client: Client, mongodb_client):
        """
        Inicializa o consumer.

        Args:
            config: Configurações da aplicação
            temporal_client: Cliente Temporal para iniciar workflows
            mongodb_client: Cliente MongoDB para buscar Cognitive Plans
        """
        self.config = config
        self.temporal_client = temporal_client
        self.mongodb_client = mongodb_client
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False

    async def initialize(self):
        """Inicializa o consumer Kafka."""
        logger.info('Inicializando Kafka consumer', topic=self.config.kafka_consensus_topic)

        self.consumer = AIOKafkaConsumer(
            self.config.kafka_consensus_topic,
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            group_id=self.config.kafka_consumer_group_id,
            auto_offset_reset=self.config.kafka_auto_offset_reset,
            enable_auto_commit=self.config.kafka_enable_auto_commit,
            value_deserializer=lambda v: json.loads(v.decode('utf-8'))
        )

        await self.consumer.start()
        logger.info('Kafka consumer inicializado com sucesso')

    async def start(self):
        """Inicia loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError('Consumer não foi inicializado. Chame initialize() primeiro.')

        logger.info('Iniciando consumo de mensagens', topic=self.config.kafka_consensus_topic)
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_message(message)
                except Exception as e:
                    logger.error(
                        'Erro ao processar mensagem',
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=True
                    )

        except Exception as e:
            logger.error('Erro no loop de consumo', error=str(e), exc_info=True)
            raise

    async def stop(self):
        """Para o consumer gracefully."""
        logger.info('Parando Kafka consumer')
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info('Kafka consumer parado')

    async def _process_message(self, message):
        """
        Processa uma mensagem do Kafka.

        Args:
            message: Mensagem do Kafka contendo ConsolidatedDecision
        """
        consolidated_decision = message.value

        logger.info(
            'Mensagem recebida do Kafka',
            topic=message.topic,
            partition=message.partition,
            offset=message.offset,
            decision_id=consolidated_decision.get('decision_id'),
            plan_id=consolidated_decision.get('plan_id')
        )

        try:
            # Validar campos obrigatórios
            required_fields = ['decision_id', 'plan_id', 'final_decision']
            for field in required_fields:
                if field not in consolidated_decision:
                    logger.error(f'Campo obrigatório ausente: {field}')
                    return

            # Verificar se decisão foi aprovada
            final_decision = consolidated_decision.get('final_decision')
            if final_decision == 'reject':
                logger.warning('Decisão foi rejeitada, não gerando tickets', decision_id=consolidated_decision['decision_id'])
                await self.consumer.commit()
                return

            if consolidated_decision.get('requires_human_review', False):
                logger.info('Decisão requer revisão humana, aguardando aprovação', decision_id=consolidated_decision['decision_id'])
                await self.consumer.commit()
                return

            # Buscar Cognitive Plan associado no MongoDB
            plan_id = consolidated_decision['plan_id']
            cognitive_plan = await self.mongodb_client.get_cognitive_plan(plan_id)

            if not cognitive_plan:
                logger.error(
                    'Cognitive Plan não encontrado no ledger',
                    plan_id=plan_id,
                    decision_id=consolidated_decision['decision_id']
                )
                # Não commitar o offset para permitir retry
                # Este é um erro que pode ser temporário (plan ainda não persistido)
                return

            # Validar campos obrigatórios do Cognitive Plan
            required_plan_fields = ['tasks', 'execution_order', 'risk_band']
            for field in required_plan_fields:
                if field not in cognitive_plan:
                    logger.error(
                        'Cognitive Plan com campos obrigatórios ausentes',
                        plan_id=plan_id,
                        missing_field=field
                    )
                    # Commitar porque este é um erro permanente
                    await self.consumer.commit()
                    return

            logger.info(
                'Cognitive Plan recuperado com sucesso',
                plan_id=plan_id,
                task_count=len(cognitive_plan.get('tasks', [])),
                risk_band=cognitive_plan.get('risk_band')
            )

            # Iniciar workflow Temporal
            workflow_id = f'{self.config.temporal_workflow_id_prefix}{plan_id}'

            input_data = {
                'consolidated_decision': consolidated_decision,
                'cognitive_plan': cognitive_plan
            }

            logger.info('Iniciando workflow Temporal', workflow_id=workflow_id, plan_id=plan_id)

            await self.temporal_client.start_workflow(
                OrchestrationWorkflow.run,
                input_data,
                id=workflow_id,
                task_queue=self.config.temporal_task_queue
            )

            logger.info('Workflow Temporal iniciado com sucesso', workflow_id=workflow_id)

            # Commit manual do offset
            await self.consumer.commit()

            logger.info('Mensagem processada com sucesso', offset=message.offset)

        except Exception as e:
            logger.error(
                'Erro ao processar mensagem',
                error=str(e),
                decision_id=consolidated_decision.get('decision_id'),
                exc_info=True
            )
            # Não commitar offset para permitir retry
            raise
