"""
ValidationProducer - Producer Kafka para publicação de SecurityValidations.

Responsável por:
- Publicar validações em security.validations
- Publicar tickets validados em execution.tickets.validated
- Publicar tickets rejeitados em execution.tickets.rejected
- Publicar tickets pendentes em execution.tickets.pending_approval
"""

from typing import Optional
import structlog
import json
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.models.security_validation import SecurityValidation

logger = structlog.get_logger(__name__)


class ValidationProducer:
    """
    Producer Kafka para publicação de validações de segurança.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str = "security.validations"
    ):
        """
        Inicializa o ValidationProducer.

        Args:
            bootstrap_servers: Servidores Kafka
            topic: Tópico principal para validações
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.producer: Optional[AIOKafkaProducer] = None

    async def connect(self) -> None:
        """
        Inicializa producer Kafka.

        Raises:
            Exception se falhar ao conectar
        """
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',  # Garantir durabilidade
                enable_idempotence=True,  # Evitar duplicatas
                max_in_flight_requests_per_connection=5
            )

            await self.producer.start()

            logger.info(
                "validation_producer.connected",
                bootstrap_servers=self.bootstrap_servers,
                topic=self.topic
            )

        except Exception as e:
            logger.error(
                "validation_producer.connection_failed",
                error=str(e)
            )
            raise

    async def close(self) -> None:
        """
        Flush e fecha producer.
        """
        if self.producer:
            await self.producer.stop()
            logger.info("validation_producer.closed")

    async def publish_validation(self, validation: SecurityValidation) -> None:
        """
        Publica SecurityValidation no tópico security.validations.

        Args:
            validation: SecurityValidation para publicar

        Raises:
            Exception se publicação falhar
        """
        if not self.producer:
            raise Exception("Producer not connected")

        try:
            # Preparar mensagem
            key = validation.validation_id
            value = validation.to_avro_dict()

            # Headers com metadados
            headers = [
                ("ticket_id", validation.ticket_id.encode('utf-8')),
                ("validation_status", validation.validation_status.value.encode('utf-8')),
                ("risk_score", str(validation.risk_assessment.risk_score).encode('utf-8')),
                ("validator_type", validation.validator_type.value.encode('utf-8'))
            ]

            # Publicar
            metadata = await self.producer.send_and_wait(
                self.topic,
                value=value,
                key=key,
                headers=headers
            )

            logger.info(
                "validation_producer.validation_published",
                validation_id=validation.validation_id,
                ticket_id=validation.ticket_id,
                topic=self.topic,
                partition=metadata.partition,
                offset=metadata.offset
            )

            # Atualizar métricas
            await self._update_metrics(self.topic, "success")

        except KafkaError as e:
            logger.error(
                "validation_producer.kafka_error",
                validation_id=validation.validation_id,
                error=str(e)
            )
            await self._update_metrics(self.topic, "error")
            raise

        except Exception as e:
            logger.error(
                "validation_producer.publish_failed",
                validation_id=validation.validation_id,
                error=str(e)
            )
            await self._update_metrics(self.topic, "error")
            raise

    async def publish_to_topic(
        self,
        topic: str,
        key: str,
        value: dict,
        headers: Optional[list] = None
    ) -> None:
        """
        Publica mensagem em tópico específico.

        Args:
            topic: Nome do tópico
            key: Chave da mensagem
            value: Valor da mensagem
            headers: Headers opcionais

        Raises:
            Exception se publicação falhar
        """
        if not self.producer:
            raise Exception("Producer not connected")

        try:
            # Publicar
            metadata = await self.producer.send_and_wait(
                topic,
                value=value,
                key=key,
                headers=headers or []
            )

            logger.info(
                "validation_producer.message_published",
                topic=topic,
                key=key,
                partition=metadata.partition,
                offset=metadata.offset
            )

            # Atualizar métricas
            await self._update_metrics(topic, "success")

        except KafkaError as e:
            logger.error(
                "validation_producer.kafka_error",
                topic=topic,
                key=key,
                error=str(e)
            )
            await self._update_metrics(topic, "error")
            raise

        except Exception as e:
            logger.error(
                "validation_producer.publish_to_topic_failed",
                topic=topic,
                key=key,
                error=str(e)
            )
            await self._update_metrics(topic, "error")
            raise

    async def _update_metrics(self, topic: str, status: str) -> None:
        """
        Atualiza métricas de publicação.

        Args:
            topic: Nome do tópico
            status: Status da publicação (success/error)
        """
        try:
            from src.observability.metrics import (
                validations_published_total
            )

            validations_published_total.labels(
                topic=topic,
                status=status
            ).inc()

        except Exception as e:
            logger.warning(
                "validation_producer.update_metrics_failed",
                error=str(e)
            )
