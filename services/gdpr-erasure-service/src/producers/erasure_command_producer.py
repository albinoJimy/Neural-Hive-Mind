"""
Produtor Kafka para Comandos de Exclusao GDPR
"""

import json

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.config.settings import Settings, get_settings

logger = structlog.get_logger()


class ErasureCommandProducer:
    """Produz comandos de exclusao para os services"""

    def __init__(self, settings: Settings):
        """
        Inicializa o produtor.

        Args:
            settings: Configuracoes
        """
        self.settings = settings
        self.producer: AIOKafkaProducer | None = None

    async def initialize(self) -> None:
        """Inicializa o produtor Kafka"""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            linger_ms=10,
            compression_type="snappy",
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self.producer.start()
        logger.info("ErasureCommandProducer inicializado")

    async def produce(self, topic: str, key: str, value: dict) -> None:
        """
        Produz mensagem no Kafka.

        Args:
            topic: Topico
            key: Chave da mensagem
            value: Valor da mensagem
        """
        if not self.producer:
            raise RuntimeError("Producer nao inicializado")

        try:
            await self.producer.send_and_wait(topic, key=key.encode(), value=value)
            logger.debug("Mensagem enviada", topic=topic, key=key)

        except KafkaError as e:
            logger.error("Erro ao enviar mensagem", topic=topic, error=str(e))
            raise

    async def close(self) -> None:
        """Fecha o produtor"""
        if self.producer:
            await self.producer.stop()
            logger.info("ErasureCommandProducer fechado")
