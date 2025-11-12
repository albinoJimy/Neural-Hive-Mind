import asyncio
import json
import os
from typing import Optional
from confluent_kafka import Producer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import structlog
from src.models.consolidated_decision import ConsolidatedDecision

logger = structlog.get_logger()


class DecisionProducer:
    '''Producer Kafka para tópico plans.consensus usando confluent-kafka'''

    def __init__(self, config):
        self.config = config
        self.producer: Optional[Producer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_serializer: Optional[AvroSerializer] = None
        self.running = False

    async def initialize(self):
        '''Inicializa producer Kafka com confluent-kafka'''
        producer_config = {
            'bootstrap.servers': self.config.kafka_bootstrap_servers,
            'enable.idempotence': self.config.kafka_enable_idempotence,
            'acks': 'all',
            'retries': 3,
            'max.in.flight.requests.per.connection': 5,
        }

        # Adicionar transactional_id se configurado
        if hasattr(self.config, 'kafka_transactional_id') and self.config.kafka_transactional_id:
            producer_config['transactional.id'] = self.config.kafka_transactional_id

        self.producer = Producer(producer_config)

        # Configurar Schema Registry para serialização Avro (opcional)
        schema_registry_url = os.getenv('SCHEMA_REGISTRY_URL')
        if schema_registry_url and schema_registry_url.strip():
            schema_path = '/app/schemas/consolidated-decision/consolidated-decision.avsc'

            if os.path.exists(schema_path):
                self.schema_registry_client = SchemaRegistryClient({'url': schema_registry_url})

                with open(schema_path, 'r') as f:
                    schema_str = f.read()

                self.avro_serializer = AvroSerializer(
                    self.schema_registry_client,
                    schema_str
                )
                logger.info('Schema Registry configurado para producer',
                           url=schema_registry_url,
                           schema_path=schema_path)
            else:
                logger.warning('Schema Avro não encontrado', path=schema_path)
                self.avro_serializer = None
        else:
            logger.warning('Schema Registry não configurado - usando JSON fallback')
            self.avro_serializer = None

        logger.info(
            'Decision producer inicializado',
            topic=self.config.kafka_consensus_topic
        )

    async def start(self, decision_queue: asyncio.Queue):
        '''Inicia loop de produção

        Args:
            decision_queue: Fila assíncrona de decisões a publicar
        '''
        if not self.producer:
            raise RuntimeError('Producer não inicializado')

        self.running = True
        logger.info('Decision producer iniciado')

        try:
            while self.running:
                try:
                    # Aguardar decisão na fila (com timeout)
                    decision = await asyncio.wait_for(
                        decision_queue.get(),
                        timeout=1.0
                    )

                    await self._publish_decision(decision)

                except asyncio.TimeoutError:
                    # Timeout é esperado, continuar loop
                    # Flush periódico para garantir entrega
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.producer.flush(timeout=0.1)
                    )
                    continue

        except Exception as e:
            logger.error('Erro no loop de produção', error=str(e))
            raise

    async def stop(self):
        '''Para producer gracefully'''
        self.running = False
        if self.producer:
            # Aguardar todas as mensagens pendentes serem enviadas
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.producer.flush(timeout=10.0)
            )
        logger.info('Decision producer parado')

    def _serialize_value(self, decision: ConsolidatedDecision):
        '''Serializa a decisão (Avro ou JSON)'''
        decision_dict = decision.to_avro_dict()

        if self.avro_serializer:
            # Serializar com Avro
            ctx = SerializationContext(self.config.kafka_consensus_topic, MessageField.VALUE)
            return self.avro_serializer(decision_dict, ctx)
        else:
            # Fallback JSON
            return json.dumps(decision_dict).encode('utf-8')

    def _delivery_callback(self, err, msg):
        '''Callback para confirmar entrega da mensagem'''
        if err:
            logger.error(
                'Erro entregando mensagem',
                error=str(err),
                topic=msg.topic(),
                partition=msg.partition() if msg else None
            )
        else:
            logger.debug(
                'Mensagem entregue',
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    async def _publish_decision(self, decision: ConsolidatedDecision):
        '''Publica decisão consolidada no Kafka'''
        try:
            # Serializar decisão
            value = self._serialize_value(decision)
            key = decision.plan_id.encode('utf-8')

            # Publicar no tópico (não-bloqueante)
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.producer.produce(
                    topic=self.config.kafka_consensus_topic,
                    key=key,
                    value=value,
                    callback=self._delivery_callback
                )
            )

            # Poll para processar callbacks de forma assíncrona
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.producer.poll(0)
            )

            logger.info(
                'Decisão publicada',
                topic=self.config.kafka_consensus_topic,
                decision_id=decision.decision_id,
                plan_id=decision.plan_id,
                final_decision=decision.final_decision.value
            )

        except Exception as e:
            logger.error(
                'Erro publicando decisão',
                decision_id=decision.decision_id,
                plan_id=decision.plan_id,
                error=str(e)
            )
            raise
