"""
Cliente Kafka Producer para publicação de Execution Tickets.
"""
import json
from typing import Dict, Any
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
import structlog

logger = structlog.get_logger()


class KafkaProducerClient:
    """Producer Kafka para publicação de tickets no tópico execution.tickets."""

    def __init__(self, config, sasl_username_override=None, sasl_password_override=None):
        """
        Inicializa o producer Kafka.

        Args:
            config: Configurações da aplicação
            sasl_username_override: Username SASL override (ex: de Vault)
            sasl_password_override: Password SASL override (ex: de Vault)
        """
        self.config = config
        self.producer = None
        self.sasl_username = sasl_username_override if sasl_username_override is not None else config.kafka_sasl_username
        self.sasl_password = sasl_password_override if sasl_password_override is not None else config.kafka_sasl_password

    async def initialize(self):
        """Inicializa o producer Kafka."""
        logger.info(
            'Inicializando Kafka producer',
            topic=self.config.kafka_tickets_topic,
            bootstrap_servers=self.config.kafka_bootstrap_servers
        )

        # Configurar producer com idempotência para garantir exactly-once semantics
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            enable_idempotence=self.config.kafka_enable_idempotence,
            acks='all',  # Aguardar confirmação de todos os replicas
            max_in_flight_requests_per_connection=5,
            retries=3,
            compression_type='gzip'
        )

        await self.producer.start()
        logger.info('Kafka producer inicializado com sucesso')

    async def publish_ticket(
        self,
        ticket: Dict[str, Any],
        topic: str = None
    ) -> Dict[str, Any]:
        """
        Publica um Execution Ticket no tópico Kafka.

        Args:
            ticket: Ticket de execução a ser publicado
            topic: Tópico Kafka (usa kafka_tickets_topic do config por padrão)

        Returns:
            Resultado da publicação contendo offset e metadata

        Raises:
            KafkaError: Em caso de falha na publicação
        """
        if not self.producer:
            raise RuntimeError('Producer não inicializado. Chame initialize() primeiro.')

        topic = topic or self.config.kafka_tickets_topic
        ticket_id = ticket['ticket_id']

        try:
            # Publicar mensagem com ticket_id como chave para garantir ordenação por ticket
            future = await self.producer.send(
                topic=topic,
                key=ticket_id,
                value=ticket
            )

            # Aguardar confirmação
            metadata = await future

            result = {
                'published': True,
                'ticket_id': ticket_id,
                'topic': metadata.topic,
                'partition': metadata.partition,
                'offset': metadata.offset,
                'timestamp': metadata.timestamp
            }

            logger.info(
                'Ticket publicado com sucesso no Kafka',
                ticket_id=ticket_id,
                topic=metadata.topic,
                partition=metadata.partition,
                offset=metadata.offset
            )

            return result

        except KafkaError as e:
            logger.error(
                'Erro ao publicar ticket no Kafka',
                ticket_id=ticket_id,
                topic=topic,
                error=str(e),
                exc_info=True
            )
            raise

    async def send(
        self,
        topic: str,
        value: Dict[str, Any],
        key: str = None
    ) -> Dict[str, Any]:
        """
        Publica uma mensagem genérica no tópico Kafka.

        Este método complementa publish_ticket() e permite publicação
        de eventos não-ticket (ex: allocation outcomes, métricas ML).

        Args:
            topic: Tópico Kafka
            value: Payload da mensagem (será serializado como JSON)
            key: Chave da mensagem (opcional)

        Returns:
            Resultado da publicação contendo offset e metadata

        Raises:
            KafkaError: Em caso de falha na publicação
        """
        if not self.producer:
            raise RuntimeError('Producer não inicializado. Chame initialize() primeiro.')

        try:
            # Publicar mensagem
            future = await self.producer.send(
                topic=topic,
                key=key,
                value=value
            )

            # Aguardar confirmação
            metadata = await future

            result = {
                'published': True,
                'topic': metadata.topic,
                'partition': metadata.partition,
                'offset': metadata.offset,
                'timestamp': metadata.timestamp
            }

            logger.debug(
                'Mensagem publicada com sucesso no Kafka',
                topic=metadata.topic,
                partition=metadata.partition,
                offset=metadata.offset,
                key=key
            )

            return result

        except KafkaError as e:
            logger.error(
                'Erro ao publicar mensagem no Kafka',
                topic=topic,
                key=key,
                error=str(e),
                exc_info=True
            )
            raise

    async def close(self):
        """Fecha o producer Kafka gracefully."""
        if self.producer:
            await self.producer.stop()
            logger.info('Kafka producer fechado')
