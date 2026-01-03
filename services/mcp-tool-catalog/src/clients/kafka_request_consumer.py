"""Kafka consumer for tool selection requests."""
import asyncio
import json
from typing import AsyncGenerator, Optional

import structlog
from aiokafka import AIOKafkaConsumer

from src.models.tool_selection import ToolSelectionRequest
from src.serialization.avro_codec import AvroCodec

logger = structlog.get_logger()


class KafkaRequestConsumer:
    """Kafka consumer for ToolSelectionRequest topic."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        session_timeout_ms: int = 30000,
        request_timeout_ms: int = 30000,
    ):
        """Initialize Kafka consumer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            topic: Topic to consume from
            group_id: Consumer group ID
            session_timeout_ms: Session timeout in milliseconds
            request_timeout_ms: Request timeout in milliseconds
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self.session_timeout_ms = session_timeout_ms
        self.request_timeout_ms = request_timeout_ms
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.avro_codec = AvroCodec()

    async def start(self, max_retries: int = 5, initial_delay: float = 1.0):
        """Start Kafka consumer with retry logic.

        Args:
            max_retries: Maximum number of connection attempts
            initial_delay: Initial delay between retries (exponential backoff)
        """
        for attempt in range(max_retries):
            try:
                logger.info(
                    "connecting_to_kafka",
                    bootstrap_servers=self.bootstrap_servers,
                    topic=self.topic,
                    attempt=attempt + 1,
                )

                self.consumer = AIOKafkaConsumer(
                    self.topic,
                    bootstrap_servers=self.bootstrap_servers,
                    group_id=self.group_id,
                    enable_auto_commit=False,
                    auto_offset_reset="earliest",
                    session_timeout_ms=self.session_timeout_ms,
                    request_timeout_ms=self.request_timeout_ms,
                )
                await self.consumer.start()

                logger.info("kafka_consumer_started", topic=self.topic)
                return

            except Exception as e:
                delay = initial_delay * (2**attempt)  # Exponential backoff
                logger.warning(
                    "kafka_consumer_connection_failed",
                    error=str(e),
                    attempt=attempt + 1,
                    retry_in_seconds=delay,
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("kafka_consumer_exhausted_retries")
                    raise

    async def stop(self):
        """Stop Kafka consumer."""
        if self.consumer:
            await self.consumer.stop()
            logger.info("kafka_consumer_stopped")

    async def consume(self) -> AsyncGenerator[ToolSelectionRequest, None]:
        """Consume and deserialize tool selection requests."""
        async for msg in self.consumer:
            try:
                # Deserialize usando AvroCodec (com fallback JSON)
                data = self.avro_codec.deserialize(msg.value, 'request')
                if not data:
                    logger.error("failed_to_deserialize_request", offset=msg.offset)
                    continue

                request = ToolSelectionRequest.from_avro(data)
                yield request
            except Exception as e:
                logger.error("message_deserialization_failed", error=str(e))

    async def commit(self):
        """Manually commit offset."""
        await self.consumer.commit()
