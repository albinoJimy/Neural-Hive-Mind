"""Consumidor base para Kafka."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

import structlog
from aiokafka import AIOKafkaConsumer

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class BaseKafkaConsumer(ABC):
    """Consumidor base Kafka com retry e error handling."""

    def __init__(self) -> None:
        """Inicializa consumidor."""
        settings = get_settings()
        self.bootstrap_servers = settings.kafka.bootstrap_servers
        self.group_id = settings.kafka.consumer_group
        self.auto_offset_reset = settings.kafka.auto_offset_reset
        self._running = False
        self._callbacks: list[Callable[[dict], Awaitable[None]]] = []

    @abstractmethod
    def get_topic(self) -> str:
        """Retorna o tópico a consumir."""

    @abstractmethod
    async def process_message(self, message: dict) -> None:
        """Processa mensagem recebida."""

    def register_callback(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        """Registra callback para processamento."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Inicia consumo de mensagens."""
        self._running = True
        consumer = AIOKafkaConsumer(
            self.get_topic(),
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            value_deserializer=lambda m: m.decode("utf-8"),
        )

        logger.info(
            "kafka_consumer_starting",
            topic=self.get_topic(),
            group_id=self.group_id,
        )

        await consumer.start()

        try:
            while self._running:
                async for msg in consumer:
                    try:
                        message_data = {"key": msg.key, "value": msg.value, "topic": msg.topic}
                        await self.process_message(message_data)

                        # Executar callbacks registrados
                        for callback in self._callbacks:
                            await callback(message_data)

                    except Exception as e:
                        logger.error(
                            "kafka_message_error",
                            error=str(e),
                            topic=msg.topic,
                            partition=msg.partition,
                            offset=msg.offset,
                        )
        finally:
            logger.info("kafka_consumer_stopping")
            await consumer.stop()

    async def stop(self) -> None:
        """Para consumo de mensagens."""
        self._running = False
        logger.info("kafka_consumer_stop_requested")
