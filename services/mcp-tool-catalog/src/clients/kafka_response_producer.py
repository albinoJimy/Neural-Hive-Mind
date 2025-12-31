"""Kafka producer for tool selection responses."""
import json
from typing import Optional

import structlog
from aiokafka import AIOKafkaProducer

from src.models.tool_selection import ToolSelectionResponse
from src.serialization.avro_codec import AvroCodec

logger = structlog.get_logger()


class KafkaResponseProducer:
    """Kafka producer for ToolSelectionResponse topic."""

    def __init__(self, bootstrap_servers: str, topic: str):
        """Initialize Kafka producer."""
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.producer: Optional[AIOKafkaProducer] = None
        self.avro_codec = AvroCodec()

    async def start(self):
        """Start Kafka producer."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            acks="all",
            compression_type="gzip",
            enable_idempotence=True,
        )
        await self.producer.start()
        logger.info("kafka_producer_started", topic=self.topic)

    async def stop(self):
        """Stop Kafka producer."""
        if self.producer:
            await self.producer.stop()
            logger.info("kafka_producer_stopped")

    async def publish_response(self, response: ToolSelectionResponse):
        """Serialize and publish tool selection response."""
        try:
            # Serialize usando AvroCodec (com fallback JSON)
            response_data = response.to_avro()
            message = self.avro_codec.serialize(response_data, 'response')
            key = response.request_id.encode("utf-8")

            await self.producer.send_and_wait(self.topic, value=message, key=key)

            logger.info(
                "response_published",
                request_id=response.request_id,
                response_id=response.response_id,
            )

        except Exception as e:
            logger.error("response_publication_failed", error=str(e), request_id=response.request_id)
            raise

    async def flush(self):
        """Flush pending messages."""
        await self.producer.flush()
