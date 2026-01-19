"""
Approval Response Consumer - Kafka consumer para respostas de aprovação

Consome respostas de aprovação do Approval Service e processa decisões
de planos cognitivos bloqueados para aprovação humana.
"""

import asyncio
import os
import structlog
import json
import time
from typing import Optional, Callable, Dict
from confluent_kafka import Consumer, KafkaError, TopicPartition
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

from src.config.settings import Settings

logger = structlog.get_logger()


# Schema Avro para deserialização de respostas de aprovação
APPROVAL_RESPONSE_SCHEMA = """
{
  "type": "record",
  "name": "ApprovalResponse",
  "namespace": "com.neuralhive.approval",
  "fields": [
    {"name": "plan_id", "type": "string"},
    {"name": "intent_id", "type": "string"},
    {"name": "decision", "type": {"type": "enum", "name": "Decision", "symbols": ["approved", "rejected"]}},
    {"name": "approved_by", "type": "string"},
    {"name": "approved_at", "type": "long"},
    {"name": "rejection_reason", "type": ["null", "string"], "default": null},
    {"name": "cognitive_plan_json", "type": ["null", "string"], "default": null}
  ]
}
"""


class ApprovalResponseConsumer:
    """Kafka consumer para respostas de aprovação de planos cognitivos"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.consumer: Optional[Consumer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_deserializer: Optional[AvroDeserializer] = None
        self.running = False
        self.last_poll_time: Optional[float] = None
        self.messages_processed: int = 0
        self._topic = settings.kafka_approval_responses_topic
        self._consumer_group = f'{settings.kafka_consumer_group_id}-approval-responses'

    async def initialize(self):
        """Inicializa Kafka consumer para respostas de aprovação"""
        logger.info(
            'Iniciando inicialização do Approval Response Consumer',
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            consumer_group=self._consumer_group,
            topic=self._topic,
            auto_offset_reset=self.settings.kafka_auto_offset_reset,
            security_protocol=self.settings.kafka_security_protocol
        )

        consumer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'group.id': self._consumer_group,
            'auto.offset.reset': self.settings.kafka_auto_offset_reset,
            'enable.auto.commit': False,  # Manual commit para exactly-once
            'isolation.level': 'read_committed',  # Exactly-once semantics
            'session.timeout.ms': self.settings.kafka_session_timeout_ms,

            # Configurações de conexão estável
            'connections.max.idle.ms': 540000,  # 9 minutos
            'socket.keepalive.enable': True,
            'heartbeat.interval.ms': 3000,
            'max.poll.interval.ms': 300000,  # 5 minutos
        }

        # Configurações de segurança
        if self.settings.kafka_security_protocol != 'PLAINTEXT':
            consumer_config.update({
                'security.protocol': self.settings.kafka_security_protocol,
                'sasl.mechanism': self.settings.kafka_sasl_mechanism,
                'sasl.username': self.settings.kafka_sasl_username,
                'sasl.password': self.settings.kafka_sasl_password,
            })

        self.consumer = Consumer(consumer_config)
        logger.info(
            'Consumer Kafka criado para respostas de aprovação',
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            consumer_group=self._consumer_group
        )

        # Validar existência do tópico antes de fazer subscribe
        logger.info('Validando existência do tópico de respostas de aprovação', topic=self._topic)

        try:
            cluster_metadata = self.consumer.list_topics(timeout=10)
            available_topics = set(cluster_metadata.topics.keys())

            if self._topic not in available_topics:
                logger.error(
                    'Tópico de respostas de aprovação não encontrado',
                    topic=self._topic,
                    available_topics=sorted(list(available_topics))[:20]
                )
                raise RuntimeError(
                    f"Tópico de aprovação não encontrado: {self._topic}. "
                    f"Verifique se o tópico foi criado no cluster."
                )

            logger.info(
                'Tópico de respostas de aprovação validado',
                topic=self._topic
            )

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(
                'Falha ao validar tópico de aprovação',
                error=str(e),
                error_type=type(e).__name__
            )
            raise RuntimeError(f"Não foi possível validar tópico de aprovação: {e}") from e

        # Subscribe ao tópico
        logger.info('Subscribing ao tópico de respostas de aprovação', topic=self._topic)
        self.consumer.subscribe([self._topic])

        # Aguardar assignments
        logger.info('Aguardando consumer assignments (timeout: 30s)')
        max_wait_seconds = 30
        poll_interval_seconds = 0.5
        start_time = time.time()
        assignments_received = False

        while time.time() - start_time < max_wait_seconds:
            msg = self.consumer.poll(timeout=0.1)

            if msg is not None and not msg.error():
                tp = TopicPartition(msg.topic(), msg.partition(), msg.offset())
                self.consumer.seek(tp)
                logger.debug(
                    'Mensagem recebida durante espera de assignments - seek realizado',
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset()
                )

            assignments = self.consumer.assignment()
            if assignments:
                assignment_info = [
                    f"{tp.topic}:{tp.partition}"
                    for tp in assignments
                ]
                logger.info(
                    'Consumer assignments recebidos',
                    assignments=assignment_info,
                    total_partitions=len(assignments),
                    elapsed_seconds=round(time.time() - start_time, 2)
                )
                assignments_received = True
                break

            await asyncio.sleep(poll_interval_seconds)

        if not assignments_received:
            logger.error(
                'Timeout aguardando consumer assignments',
                timeout_seconds=max_wait_seconds,
                consumer_group=self._consumer_group,
                topic=self._topic
            )
            raise RuntimeError(
                f"Consumer não recebeu assignments após {max_wait_seconds}s. "
                f"Verifique se o consumer group '{self._consumer_group}' "
                f"está configurado corretamente."
            )

        # Inicializar Schema Registry (opcional)
        if self.settings.schema_registry_url and self.settings.schema_registry_url.strip():
            try:
                self.schema_registry_client = SchemaRegistryClient({'url': self.settings.schema_registry_url})
                self.avro_deserializer = AvroDeserializer(
                    self.schema_registry_client,
                    APPROVAL_RESPONSE_SCHEMA
                )
                logger.info(
                    'Schema Registry habilitado para approval response consumer',
                    url=self.settings.schema_registry_url
                )
            except Exception as e:
                logger.warning(
                    'Falha ao inicializar Schema Registry - usando JSON',
                    error=str(e)
                )
                self.schema_registry_client = None
                self.avro_deserializer = None
        else:
            logger.warning('Schema Registry desabilitado - usando deserialização JSON para dev')
            self.schema_registry_client = None
            self.avro_deserializer = None

        logger.info(
            'Approval Response Consumer inicializado com sucesso',
            topic=self._topic,
            group_id=self._consumer_group,
            assignments=len(self.consumer.assignment()) if self.consumer else 0,
            schema_registry_enabled=self.avro_deserializer is not None
        )

    async def start_consuming(self, processor_callback: Callable):
        """
        Inicia loop de consumo de mensagens

        Args:
            processor_callback: Função async para processar resposta de aprovação
        """
        self.running = True

        logger.info('Iniciando consumer loop de respostas de aprovação')

        await self._consume_async_loop(processor_callback)

        logger.info('Consumer loop de aprovação encerrado')

    async def _consume_async_loop(self, processor_callback: Callable):
        """
        Loop assíncrono de consumo com poll não-bloqueante

        Args:
            processor_callback: Função async para processar resposta de aprovação
        """
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="kafka-approval-poller"
        )

        poll_count = 0
        logger.info('Consumer loop de aprovação inicializado, iniciando poll...')

        while self.running:
            try:
                loop = asyncio.get_running_loop()
                msg = await loop.run_in_executor(
                    executor,
                    self.consumer.poll,
                    1.0
                )

                poll_count += 1
                self.last_poll_time = time.time()

                if poll_count % 60 == 0:
                    logger.debug(f'Approval consumer loop ativo, poll count: {poll_count}')

                if msg is None:
                    await asyncio.sleep(0.1)
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error('Kafka approval consumer error', error=msg.error())
                        continue

                logger.info(
                    'Mensagem de aprovação recebida',
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset()
                )

                # Deserializar mensagem
                approval_response = self._deserialize_message(msg)

                # Extrair trace context
                trace_context = self._extract_trace_context(msg.headers() or [])

                # Processar mensagem
                try:
                    await processor_callback(approval_response, trace_context)

                    # Commit offset após processamento bem-sucedido
                    await loop.run_in_executor(
                        executor,
                        lambda: self.consumer.commit(asynchronous=False)
                    )

                    self.messages_processed += 1
                    logger.debug(
                        'Resposta de aprovação processada',
                        plan_id=approval_response.get('plan_id'),
                        decision=approval_response.get('decision'),
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset(),
                        total_processed=self.messages_processed
                    )

                except Exception as e:
                    logger.error(
                        'Erro ao processar resposta de aprovação',
                        error=str(e),
                        plan_id=approval_response.get('plan_id') if approval_response else None
                    )
                    # Não faz commit - mensagem será retentada

            except Exception as e:
                logger.error('Erro no consumer loop de aprovação', error=str(e))
                await asyncio.sleep(1.0)

        executor.shutdown(wait=True)

    def _deserialize_message(self, msg) -> Dict:
        """
        Deserializa mensagem Kafka para ApprovalResponse

        Suporta deserialização Avro (via Schema Registry) e JSON fallback.

        Args:
            msg: Mensagem Kafka

        Returns:
            Dict com dados da resposta de aprovação
        """
        try:
            headers = msg.headers() or []
            content_type = None
            for key, value in headers:
                if key == 'content-type':
                    content_type = value.decode('utf-8') if value else None
                    break

            if content_type == 'application/avro' and self.avro_deserializer:
                serialization_context = SerializationContext(msg.topic(), MessageField.VALUE)
                data = self.avro_deserializer(msg.value(), serialization_context)

                logger.debug(
                    'Mensagem de aprovação deserializada (Avro)',
                    plan_id=data.get('plan_id'),
                    decision=data.get('decision')
                )
            else:
                data = json.loads(msg.value().decode('utf-8'))

                logger.debug(
                    'Mensagem de aprovação deserializada (JSON fallback)',
                    plan_id=data.get('plan_id'),
                    decision=data.get('decision'),
                    content_type=content_type
                )

            # Parsear cognitive_plan_json se presente
            if data.get('cognitive_plan_json'):
                try:
                    data['cognitive_plan'] = json.loads(data['cognitive_plan_json'])
                except json.JSONDecodeError:
                    logger.warning(
                        'Falha ao parsear cognitive_plan_json',
                        plan_id=data.get('plan_id')
                    )
                    data['cognitive_plan'] = None

            return data

        except Exception as e:
            logger.error('Erro ao deserializar mensagem de aprovação', error=str(e))
            raise

    def _extract_trace_context(self, headers: list) -> Dict[str, str]:
        """
        Extrai contexto de rastreamento dos headers Kafka

        Args:
            headers: Headers da mensagem Kafka

        Returns:
            Dict com trace context
        """
        trace_context = {}

        for key, value in headers:
            if key == 'trace-id':
                trace_context['trace_id'] = value.decode('utf-8')
            elif key == 'span-id':
                trace_context['span_id'] = value.decode('utf-8')
            elif key == 'correlation-id':
                trace_context['correlation_id'] = value.decode('utf-8')

        logger.debug(
            'Trace context extraído dos headers Kafka',
            trace_id=trace_context.get('trace_id'),
            span_id=trace_context.get('span_id'),
            correlation_id=trace_context.get('correlation_id'),
            total_headers=len(headers)
        )

        return trace_context

    async def close(self):
        """Fecha consumer gracefully"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info('Approval Response Consumer fechado')

    def is_healthy(self, max_poll_age_seconds: float = 60.0) -> tuple[bool, str]:
        """
        Verifica se o consumer está saudável baseado em atividade recente.

        Args:
            max_poll_age_seconds: Tempo máximo em segundos desde o último poll

        Returns:
            Tuple de (is_healthy, reason)
        """
        if not self.running:
            return False, "Consumer não está em estado running"

        if not self.consumer:
            return False, "Consumer Kafka não inicializado"

        if self.last_poll_time is None:
            return False, "Consumer ainda não iniciou polling"

        poll_age = time.time() - self.last_poll_time
        if poll_age > max_poll_age_seconds:
            return False, f"Último poll há {poll_age:.1f}s (máx: {max_poll_age_seconds}s)"

        return True, f"Consumer ativo (último poll há {poll_age:.1f}s, {self.messages_processed} msgs processadas)"
