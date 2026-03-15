import asyncio
import json
import os
import time
from typing import Optional, Set
from confluent_kafka import Producer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import structlog
from src.models.consolidated_decision import ConsolidatedDecision

# F5: OpenTelemetry W3C traceparent support
try:
    from neural_hive_observability.context import ContextManager
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    ContextManager = None

logger = structlog.get_logger()


class DecisionProducer:
    '''Producer Kafka para tópico plans.consensus usando confluent-kafka'''

    def __init__(self, config, context_manager: Optional[ContextManager] = None):
        self.config = config
        self.producer: Optional[Producer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_serializer: Optional[AvroSerializer] = None
        self.running = False
        self.context_manager = context_manager

        # Deduplicação: cache de plan_id já processados
        self._processed_plan_ids: Set[str] = set()
        self._processed_plan_timestamps: dict = {}
        self._deduplication_ttl = 24 * 60 * 60  # 24 horas em segundos

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

        # Configuração de segurança SASL (se não for PLAINTEXT)
        if self.config.kafka_security_protocol != 'PLAINTEXT':
            producer_config['security.protocol'] = self.config.kafka_security_protocol
            if self.config.kafka_sasl_mechanism:
                producer_config['sasl.mechanism'] = self.config.kafka_sasl_mechanism
            if self.config.kafka_sasl_username:
                producer_config['sasl.username'] = self.config.kafka_sasl_username
            if self.config.kafka_sasl_password:
                producer_config['sasl.password'] = self.config.kafka_sasl_password

            logger.info(
                'Configuração de segurança SASL aplicada ao producer',
                security_protocol=self.config.kafka_security_protocol,
                sasl_mechanism=self.config.kafka_sasl_mechanism
            )

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
            # Validação defensiva - correlation_id deve sempre existir
            if not decision.correlation_id or not decision.correlation_id.strip():
                logger.error(
                    'CRITICAL: correlation_id ausente na decisão - violação de contrato',
                    decision_id=decision.decision_id,
                    plan_id=decision.plan_id,
                    intent_id=decision.intent_id
                )
                raise ValueError(
                    f"correlation_id não pode ser None/vazio. "
                    f"decision_id={decision.decision_id}, plan_id={decision.plan_id}"
                )

            # DEDUPLICAÇÃO: Verificar se plan_id já foi processado
            plan_id = decision.plan_id
            if plan_id:
                if plan_id in self._processed_plan_ids:
                    logger.warning(
                        'decision_already_published - skipping duplicate',
                        plan_id=plan_id,
                        decision_id=decision.decision_id,
                        existing_timestamp=self._processed_plan_timestamps.get(plan_id),
                        final_decision=decision.final_decision.value if hasattr(decision.final_decision, 'value') else str(decision.final_decision)
                    )
                    return  # Não republicar decisão duplicada

                # Marcar como processado
                self._processed_plan_ids.add(plan_id)
                self._processed_plan_timestamps[plan_id] = time.time()

                # Limpar entradas antigas (> TTL)
                self._cleanup_old_plans()

            # Serializar decisão
            value = self._serialize_value(decision)
            key = decision.plan_id.encode('utf-8')

            # F5: Preparar headers com W3C traceparent propagation
            headers = {
                'decision-id': decision.decision_id,
                'plan-id': decision.plan_id,
                'intent-id': decision.intent_id,
                'correlation-id': decision.correlation_id,
                'final-decision': decision.final_decision.value if hasattr(decision.final_decision, 'value') else str(decision.final_decision),
            }

            # Injetar contexto OpenTelemetry W3C traceparent via ContextManager
            if self.context_manager and OBSERVABILITY_AVAILABLE:
                headers_dict = self.context_manager.inject_http_headers(headers)
                # Converter de volta para formato lista de tuplas do confluent-kafka
                kafka_headers = [(k, v.encode('utf-8') if isinstance(v, str) else v)
                               for k, v in headers_dict.items()]
            else:
                # Fallback: headers básicos sem ContextManager
                kafka_headers = [(k, v.encode('utf-8') if isinstance(v, str) else v)
                               for k, v in headers.items()]

            # Publicar no tópico (não-bloqueante)
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.producer.produce(
                    topic=self.config.kafka_consensus_topic,
                    key=key,
                    value=value,
                    headers=kafka_headers,
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
                correlation_id=decision.correlation_id,
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

    def _cleanup_old_plans(self):
        """Remove plan_ids antigos do cache de deduplicação.

        Mantém apenas os plan_id das últimas 24 horas para evitar
        crescimento ilimitado do cache em memória.
        """
        current_time = time.time()
        cutoff = current_time - self._deduplication_ttl

        # Encontrar plan_ids antigos
        old_plan_ids = [
            plan_id
            for plan_id, timestamp in self._processed_plan_timestamps.items()
            if timestamp < cutoff
        ]

        # Remover do cache
        for plan_id in old_plan_ids:
            self._processed_plan_ids.discard(plan_id)
            del self._processed_plan_timestamps[plan_id]

        if old_plan_ids:
            logger.info(
                'cleaned_old_plan_ids_from_deduplication_cache',
                count=len(old_plan_ids),
                ttl_hours=self._deduplication_ttl / 3600
            )
