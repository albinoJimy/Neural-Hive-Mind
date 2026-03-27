"""Gerenciamento de ciclo de vida dos consumidores Kafka."""

import asyncio
from src.consumers.base import BaseKafkaConsumer
import structlog

logger = structlog.get_logger(__name__)


class ConsumerManager:
    """Gerencia múltiplos consumidores Kafka."""

    def __init__(self) -> None:
        """Inicializa gerenciador."""
        self.consumers: list[BaseKafkaConsumer] = []
        self._tasks: list[asyncio.Task] = []

    def register(self, consumer: BaseKafkaConsumer) -> None:
        """Registra consumidor."""
        self.consumers.append(consumer)
        logger.info(
            "consumer_registered",
            consumer=consumer.__class__.__name__,
            topic=consumer.get_topic(),
        )

    async def start_all(self) -> None:
        """Inicia todos os consumidores."""
        for consumer in self.consumers:
            task = asyncio.create_task(consumer.start())
            self._tasks.append(task)

        logger.info(
            "all_consumers_started",
            count=len(self.consumers),
        )

        # Aguardar tarefas (indefinidamente)
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Para todos os consumidores."""
        for consumer in self.consumers:
            await consumer.stop()

        # Cancelar tarefas
        for task in self._tasks:
            if not task.done():
                task.cancel()

        logger.info("all_consumers_stopped")
