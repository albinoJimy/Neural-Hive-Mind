"""Kafka consumer for tool selection requests."""
import json
from typing import AsyncGenerator, Optional

import structlog
from aiokafka import AIOKafkaConsumer

from src.models.tool_selection import ToolSelectionRequest
from src.serialization.avro_codec import AvroCodec

logger = structlog.get_logger()


class KafkaRequestConsumer:
    """Kafka consumer for ToolSelectionRequest topic."""

    def __init__(self, bootstrap_servers: str, topic: str, group_id: str):
        """Initialize Kafka consumer."""
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.avro_codec = AvroCodec()

    async def start(self):
        """Start Kafka consumer."""
        self.consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            session_timeout_ms=30000,
        )
        await self.consumer.start()
        logger.info("kafka_consumer_started", topic=self.topic)

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
