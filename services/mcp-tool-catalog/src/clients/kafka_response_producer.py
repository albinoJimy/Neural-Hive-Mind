"""Kafka producer for tool selection responses."""
import asyncio
import json
from typing import Optional

import structlog
from aiokafka import AIOKafkaProducer

from src.models.tool_selection import ToolSelectionResponse
from src.serialization.avro_codec import AvroCodec

logger = structlog.get_logger()


class KafkaResponseProducer:
    """Kafka producer for ToolSelectionResponse topic."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        request_timeout_ms: int = 30000,
    ):
        """Initialize Kafka producer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            topic: Topic to produce to
            request_timeout_ms: Request timeout in milliseconds
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.request_timeout_ms = request_timeout_ms
        self.producer: Optional[AIOKafkaProducer] = None
        self.avro_codec = AvroCodec()

    async def start(self, max_retries: int = 5, initial_delay: float = 1.0):
        """Start Kafka producer with retry logic.

        Args:
            max_retries: Maximum number of connection attempts
            initial_delay: Initial delay between retries (exponential backoff)
        """
        for attempt in range(max_retries):
            try:
                logger.info(
                    "connecting_to_kafka_producer",
                    bootstrap_servers=self.bootstrap_servers,
                    topic=self.topic,
                    attempt=attempt + 1,
                )

                self.producer = AIOKafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    acks="all",
                    compression_type="gzip",
                    enable_idempotence=True,
                    request_timeout_ms=self.request_timeout_ms,
                )
                await self.producer.start()

                logger.info("kafka_producer_started", topic=self.topic)
                return

            except Exception as e:
                delay = initial_delay * (2**attempt)  # Exponential backoff
                logger.warning(
                    "kafka_producer_connection_failed",
                    error=str(e),
                    attempt=attempt + 1,
                    retry_in_seconds=delay,
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("kafka_producer_exhausted_retries")
                    raise

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
