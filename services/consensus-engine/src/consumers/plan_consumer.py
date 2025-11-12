import asyncio
import json
import os
from typing import Dict, Any, Optional
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
import structlog
from src.services.consensus_orchestrator import ConsensusOrchestrator

logger = structlog.get_logger()


class PlanConsumer:
    '''Consumer Kafka para tópico plans.ready usando confluent-kafka'''

    def __init__(self, config, specialists_client, mongodb_client, pheromone_client):
        self.config = config
        self.specialists_client = specialists_client
        self.mongodb_client = mongodb_client
        self.orchestrator = ConsensusOrchestrator(config, pheromone_client)
        self.consumer: Optional[Consumer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_deserializer: Optional[AvroDeserializer] = None
        self.running = False

    async def initialize(self):
        '''Inicializa consumer Kafka com confluent-kafka'''
        consumer_config = {
            'bootstrap.servers': self.config.kafka_bootstrap_servers,
            'group.id': self.config.kafka_consumer_group_id,
            'auto.offset.reset': self.config.kafka_auto_offset_reset,
            'enable.auto.commit': self.config.kafka_enable_auto_commit,
        }

        self.consumer = Consumer(consumer_config)
        self.consumer.subscribe([self.config.kafka_plans_topic])

        # Configurar Schema Registry para deserialização Avro
        schema_registry_url = os.getenv('SCHEMA_REGISTRY_URL')
        if schema_registry_url and schema_registry_url.strip():
            schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'

            if os.path.exists(schema_path):
                self.schema_registry_client = SchemaRegistryClient({'url': schema_registry_url})

                with open(schema_path, 'r') as f:
                    schema_str = f.read()

                self.avro_deserializer = AvroDeserializer(
                    self.schema_registry_client,
                    schema_str
                )
                logger.info('Schema Registry configurado para consumer',
                           url=schema_registry_url,
                           schema_path=schema_path)
            else:
                logger.warning('Schema Avro não encontrado', path=schema_path)
                self.avro_deserializer = None
        else:
            logger.warning('Schema Registry não configurado - usando JSON fallback')
            self.avro_deserializer = None

        logger.info(
            'Plan consumer inicializado',
            topic=self.config.kafka_plans_topic,
            group_id=self.config.kafka_consumer_group_id
        )

    async def start(self):
        '''Inicia loop de consumo com confluent-kafka'''
        if not self.consumer:
            raise RuntimeError('Consumer não inicializado')

        self.running = True
        logger.info('Plan consumer iniciado')

        try:
            while self.running:
                # Poll com timeout de 1 segundo (non-blocking)
                msg = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.consumer.poll(timeout=1.0)
                )

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug('Reached end of partition')
                        continue
                    else:
                        logger.error('Erro no consumer', error=msg.error())
                        raise Exception(msg.error())

                # Deserializar mensagem
                cognitive_plan = self._deserialize_value(msg)

                if cognitive_plan:
                    await self._process_message(msg, cognitive_plan)

        except Exception as e:
            logger.error('Erro no loop de consumo', error=str(e))
            raise
        finally:
            logger.info('Consumer loop finalizado')

    def _deserialize_value(self, msg):
        '''Deserializa o valor da mensagem (Avro ou JSON)'''
        try:
            if self.avro_deserializer:
                # Deserializar com Avro
                ctx = SerializationContext(msg.topic(), MessageField.VALUE)
                return self.avro_deserializer(msg.value(), ctx)
            else:
                # Fallback JSON
                return json.loads(msg.value().decode('utf-8'))
        except Exception as e:
            logger.error('Erro deserializando mensagem',
                        error=str(e),
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset())
            return None

    async def stop(self):
        '''Para consumer gracefully'''
        self.running = False
        if self.consumer:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.consumer.close
            )
        logger.info('Plan consumer parado')

    async def _process_message(self, msg, cognitive_plan):
        '''Processa mensagem do Kafka'''
        try:
            logger.info(
                'Mensagem recebida',
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                plan_id=cognitive_plan.get('plan_id')
            )

            # 1. Invocar especialistas via gRPC
            specialist_opinions = await self._invoke_specialists(cognitive_plan)

            # 2. Processar consenso
            decision = await self.orchestrator.process_consensus(
                cognitive_plan,
                specialist_opinions
            )

            # 3. Persistir no ledger (MongoDB)
            await self.mongodb_client.save_consensus_decision(decision)

            logger.info(
                'Decisao salva no ledger',
                decision_id=decision.decision_id,
                plan_id=cognitive_plan['plan_id'],
                final_decision=decision.final_decision.value
            )

            # 4. Publicar decisão no Kafka (será feito pelo producer)
            # Armazenar na fila de produção
            from src.main import state
            if hasattr(state, 'decision_queue'):
                await state.decision_queue.put(decision)

            # 5. Commit manual do offset
            if not self.config.kafka_enable_auto_commit:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.consumer.commit(msg)
                )

            logger.info(
                'Mensagem processada com sucesso',
                plan_id=cognitive_plan['plan_id'],
                decision_id=decision.decision_id,
                final_decision=decision.final_decision.value
            )

        except Exception as e:
            logger.error(
                'Erro processando mensagem',
                error=str(e),
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )
            # Não commitar offset em caso de erro (permitir retry)
            raise

    async def _invoke_specialists(self, cognitive_plan: Dict[str, Any]):
        '''Invoca todos os especialistas em paralelo via gRPC'''
        logger.info(
            'Invocando especialistas',
            plan_id=cognitive_plan['plan_id']
        )

        # Extrair trace context das mensagens Kafka ou criar novo
        trace_context = {
            'trace_id': cognitive_plan.get('trace_id', ''),
            'span_id': cognitive_plan.get('span_id', '')
        }

        # Invocar todos em paralelo se habilitado
        if self.config.enable_parallel_invocation:
            opinions = await self.specialists_client.evaluate_plan_parallel(
                cognitive_plan,
                trace_context
            )
        else:
            # Sequencial (fallback)
            opinions = []
            for specialist_type in ['business', 'technical', 'behavior', 'evolution', 'architecture']:
                try:
                    opinion = await self.specialists_client.evaluate_plan(
                        specialist_type,
                        cognitive_plan,
                        trace_context
                    )
                    opinions.append(opinion)
                except Exception as e:
                    logger.error(
                        'Erro invocando especialista',
                        specialist_type=specialist_type,
                        error=str(e)
                    )

        logger.info(
            'Especialistas invocados',
            plan_id=cognitive_plan['plan_id'],
            num_opinions=len(opinions)
        )

        return opinions
