"""
Approval Request Consumer - Kafka consumer para requests de aprovacao

Consome Cognitive Plans que requerem aprovacao humana do topico de requests.
"""

import os
import json
import asyncio
import structlog
from datetime import datetime
from typing import Optional, Callable, Awaitable
from confluent_kafka import Consumer, KafkaError, Message
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from pymongo.errors import DuplicateKeyError

from src.config.settings import Settings
from src.models.approval import ApprovalRequest, RiskBand

logger = structlog.get_logger()


class ApprovalRequestConsumer:
    """Kafka consumer para requests de aprovacao de planos"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.consumer: Optional[Consumer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_deserializer: Optional[AvroDeserializer] = None
        self.running: bool = False
        self._last_poll_time: Optional[datetime] = None

    async def initialize(self):
        """Inicializa consumer Kafka com suporte a Schema Registry"""
        consumer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'group.id': self.settings.kafka_consumer_group_id,
            'auto.offset.reset': self.settings.kafka_auto_offset_reset,
            'enable.auto.commit': self.settings.kafka_enable_auto_commit,
            'session.timeout.ms': self.settings.kafka_session_timeout_ms,
            'max.poll.interval.ms': self.settings.kafka_max_poll_interval_ms,
            'isolation.level': 'read_committed',
        }

        # Adiciona configuracao de seguranca
        if self.settings.kafka_security_protocol != 'PLAINTEXT':
            consumer_config.update({
                'security.protocol': self.settings.kafka_security_protocol,
                'sasl.mechanism': self.settings.kafka_sasl_mechanism,
                'sasl.username': self.settings.kafka_sasl_username,
                'sasl.password': self.settings.kafka_sasl_password,
            })

        self.consumer = Consumer(consumer_config)

        # Inicializa Schema Registry client (opcional para dev)
        if self.settings.schema_registry_url and self.settings.schema_registry_url.strip():
            schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'
            logger.info(
                'Inicializando Schema Registry para approval consumer',
                url=self.settings.schema_registry_url,
                schema_path=schema_path
            )

            if os.path.exists(schema_path):
                logger.info('Schema Avro encontrado', path=schema_path)
                self.schema_registry_client = SchemaRegistryClient({
                    'url': self.settings.schema_registry_url
                })

                # Carrega schema Avro
                with open(schema_path, 'r') as f:
                    schema_str = f.read()

                self.avro_deserializer = AvroDeserializer(
                    self.schema_registry_client,
                    schema_str
                )
                logger.info(
                    'Schema Registry habilitado para consumer',
                    url=self.settings.schema_registry_url,
                    deserializer_type='AvroDeserializer'
                )
            else:
                logger.warning(
                    'Schema Avro nao encontrado - fallback para JSON',
                    path=schema_path
                )
        else:
            logger.warning(
                'Schema Registry desabilitado - usando JSON',
                environment=self.settings.environment
            )

        # Subscribe no topico
        self.consumer.subscribe([self.settings.kafka_approval_requests_topic])

        logger.info(
            'Approval Request Consumer inicializado',
            group_id=self.settings.kafka_consumer_group_id,
            topic=self.settings.kafka_approval_requests_topic
        )

    async def start_consuming(
        self,
        process_callback: Callable[[ApprovalRequest], Awaitable[None]]
    ):
        """
        Inicia consumo de mensagens de aprovacao

        Args:
            process_callback: Funcao async para processar cada ApprovalRequest
        """
        self.running = True
        logger.info('Iniciando consumo de approval requests')

        while self.running:
            try:
                # Poll com timeout de 1 segundo
                msg: Optional[Message] = self.consumer.poll(timeout=1.0)
                self._last_poll_time = datetime.utcnow()

                if msg is None:
                    await asyncio.sleep(0.1)
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug(
                            'Fim da particao atingido',
                            partition=msg.partition()
                        )
                    else:
                        logger.error(
                            'Erro no consumer Kafka',
                            error=msg.error()
                        )
                    continue

                # Deserializa mensagem
                try:
                    approval_request = await self._deserialize_message(msg)
                    if approval_request:
                        # Processa mensagem
                        await process_callback(approval_request)
                        # Commit manual
                        self.consumer.commit(message=msg)
                        logger.debug(
                            'Mensagem processada e commitada',
                            plan_id=approval_request.plan_id
                        )
                except DuplicateKeyError as e:
                    # Plan ja existe - comita para pular duplicata
                    self.consumer.commit(message=msg)
                    logger.warning(
                        'Mensagem duplicada detectada - commitando para pular',
                        plan_id=approval_request.plan_id if approval_request else 'unknown',
                        offset=msg.offset()
                    )
                except Exception as e:
                    logger.error(
                        'Erro ao processar mensagem de aprovacao',
                        error=str(e),
                        offset=msg.offset()
                    )
                    # Nao comita mensagem com erro para retry

            except Exception as e:
                logger.error(
                    'Erro no loop de consumo',
                    error=str(e)
                )
                await asyncio.sleep(1.0)

    async def _deserialize_message(self, msg: Message) -> Optional[ApprovalRequest]:
        """
        Deserializa mensagem Kafka para ApprovalRequest

        Args:
            msg: Mensagem Kafka

        Returns:
            ApprovalRequest ou None se falhar
        """
        try:
            # Extrai headers
            headers = {}
            if msg.headers():
                headers = {k: v.decode('utf-8') if v else None for k, v in msg.headers()}

            # Deserializa valor
            if self.avro_deserializer:
                ctx = SerializationContext(msg.topic(), MessageField.VALUE)
                plan_data = self.avro_deserializer(msg.value(), ctx)
            else:
                # Fallback para JSON
                plan_data = json.loads(msg.value().decode('utf-8'))

            # Extrai dados relevantes
            risk_band_value = plan_data.get('risk_band', 'high')
            if isinstance(risk_band_value, str):
                risk_band = RiskBand(risk_band_value)
            else:
                risk_band = RiskBand.HIGH

            approval_request = ApprovalRequest(
                plan_id=plan_data.get('plan_id'),
                intent_id=plan_data.get('intent_id'),
                risk_score=plan_data.get('risk_score', 0.0),
                risk_band=risk_band,
                is_destructive=plan_data.get('is_destructive', False),
                destructive_tasks=plan_data.get('destructive_tasks', []),
                risk_matrix=plan_data.get('risk_matrix'),
                cognitive_plan=plan_data
            )

            logger.info(
                'Mensagem deserializada com sucesso',
                plan_id=approval_request.plan_id,
                intent_id=approval_request.intent_id,
                risk_band=risk_band_value,
                is_destructive=approval_request.is_destructive
            )

            return approval_request

        except Exception as e:
            logger.error(
                'Falha ao deserializar mensagem',
                error=str(e),
                offset=msg.offset()
            )
            return None

    def is_healthy(self, max_poll_age_seconds: float = 60.0) -> tuple:
        """
        Verifica saude do consumer

        Args:
            max_poll_age_seconds: Idade maxima do ultimo poll

        Returns:
            Tuple (is_healthy: bool, reason: str)
        """
        if not self.running:
            return False, 'Consumer nao esta rodando'

        if not self.consumer:
            return False, 'Consumer nao inicializado'

        if self._last_poll_time:
            age = (datetime.utcnow() - self._last_poll_time).total_seconds()
            if age > max_poll_age_seconds:
                return False, f'Ultimo poll ha {age:.1f}s (max: {max_poll_age_seconds}s)'

        return True, 'Consumer saudavel'

    async def close(self):
        """Fecha consumer gracefully"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info('Approval Request Consumer fechado')
