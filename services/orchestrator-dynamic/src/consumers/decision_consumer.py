"""
Kafka consumer para tópico plans.consensus.
Consome decisões consolidadas e inicia workflows Temporal.

Suporta deserialização Avro (Confluent wire format) e JSON fallback.
"""
import json
import io
import os
from typing import Optional

from aiokafka import AIOKafkaConsumer
from temporalio.client import Client
import structlog

# Avro support
try:
    from confluent_kafka.schema_registry import SchemaRegistryClient
    import fastavro
    AVRO_AVAILABLE = True
except ImportError:
    AVRO_AVAILABLE = False

from src.workflows.orchestration_workflow import OrchestrationWorkflow

logger = structlog.get_logger()


def _deserialize_avro_or_json(raw_bytes: bytes, schema_registry_url: str = None) -> dict:
    """
    Deserialize message supporting both Avro (Confluent wire format) and JSON.

    Confluent wire format:
    - Byte 0: Magic byte (0x00)
    - Bytes 1-4: Schema ID (big-endian int)
    - Bytes 5+: Avro payload
    """
    if len(raw_bytes) < 5:
        # Too short for Avro wire format, try JSON
        return json.loads(raw_bytes.decode('utf-8'))

    magic_byte = raw_bytes[0]
    if magic_byte != 0:
        # Not Avro wire format, try JSON
        return json.loads(raw_bytes.decode('utf-8'))

    # Extract schema ID and Avro payload
    schema_id = int.from_bytes(raw_bytes[1:5], byteorder='big')
    avro_payload = raw_bytes[5:]

    if AVRO_AVAILABLE:
        try:
            reader = io.BytesIO(avro_payload)
            records = list(fastavro.reader(reader))
            if records:
                return records[0]
        except Exception as e:
            # Fallback: try with schema from registry
            if schema_registry_url:
                try:
                    client = SchemaRegistryClient({'url': schema_registry_url})
                    schema = client.get_schema(schema_id)
                    parsed_schema = fastavro.parse_schema(json.loads(schema.schema_str))
                    reader = io.BytesIO(avro_payload)
                    return fastavro.schemaless_reader(reader, parsed_schema)
                except Exception as registry_error:
                    logger.warning("schema_registry_fallback_failed", error=str(registry_error))
            raise e

    raise ValueError("Avro deserialization not available")


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
        self.schema_registry_url = os.getenv(
            'SCHEMA_REGISTRY_URL',
            'http://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v6'
        )

    async def initialize(self):
        """Inicializa o consumer Kafka."""
        logger.info('Inicializando Kafka consumer', topic=self.config.kafka_consensus_topic)

        # Não usar value_deserializer - deserialização manual para suportar Avro e JSON
        self.consumer = AIOKafkaConsumer(
            self.config.kafka_consensus_topic,
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            group_id=self.config.kafka_consumer_group_id,
            auto_offset_reset=self.config.kafka_auto_offset_reset,
            enable_auto_commit=self.config.kafka_enable_auto_commit,
            # Recebemos bytes crus para deserialização manual (Avro/JSON)
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
        # Deserializar mensagem (suporta Avro e JSON)
        raw_value = message.value
        if isinstance(raw_value, bytes):
            try:
                consolidated_decision = _deserialize_avro_or_json(
                    raw_value,
                    self.schema_registry_url
                )
            except Exception as deser_err:
                logger.warning(
                    "avro_deserialization_failed_trying_json",
                    error=str(deser_err)
                )
                # Fallback para JSON
                consolidated_decision = json.loads(raw_value.decode('utf-8'))
        else:
            consolidated_decision = raw_value

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
