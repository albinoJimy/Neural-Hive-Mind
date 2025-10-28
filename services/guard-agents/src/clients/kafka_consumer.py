"""Kafka consumer for Guard Agents"""
import asyncio
from typing import Callable, Optional
from aiokafka import AIOKafkaConsumer
import structlog

logger = structlog.get_logger()


class KafkaConsumerClient:
    """Cliente Kafka consumer assíncrono para Guard Agents"""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = False
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.topics = topics
        self.auto_offset_reset = auto_offset_reset
        self.enable_auto_commit = enable_auto_commit

        self.consumer: Optional[AIOKafkaConsumer] = None
        self._consume_task: Optional[asyncio.Task] = None
        self._running = False
        self._message_handler: Optional[Callable] = None

    async def connect(self):
        """Conecta ao Kafka"""
        try:
            self.consumer = AIOKafkaConsumer(
                *self.topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset=self.auto_offset_reset,
                enable_auto_commit=self.enable_auto_commit
            )
            await self.consumer.start()
            logger.info("kafka.consumer_connected", topics=self.topics, group_id=self.group_id)
        except Exception as e:
            logger.error("kafka.consumer_connection_failed", error=str(e))
            raise

    def set_message_handler(self, handler: Callable):
        """Define handler para processar mensagens"""
        self._message_handler = handler

    async def start_consuming(self):
        """Inicia consumo de mensagens"""
        if not self._message_handler:
            raise ValueError("Message handler not set. Call set_message_handler() first.")

        self._running = True
        self._consume_task = asyncio.create_task(self._consume_loop())
        logger.info("kafka.consumer_started", topics=self.topics)

    async def _consume_loop(self):
        """Loop de consumo de mensagens"""
        try:
            async for msg in self.consumer:
                if not self._running:
                    break

                try:
                    await self._message_handler(msg)

                    if not self.enable_auto_commit:
                        await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        "kafka.message_processing_failed",
                        topic=msg.topic,
                        partition=msg.partition,
                        offset=msg.offset,
                        error=str(e)
                    )
        except Exception as e:
            logger.error("kafka.consume_loop_failed", error=str(e))

    async def stop(self):
        """Para consumo de mensagens"""
        self._running = False
        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        if self.consumer:
            await self.consumer.stop()

        logger.info("kafka.consumer_stopped")

    def is_healthy(self) -> bool:
        """Verifica se consumer está saudável"""
        return self.consumer is not None and self._running
