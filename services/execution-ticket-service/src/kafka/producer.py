"""Kafka Producer for publishing tickets to execution.tickets topic.

This module provides a producer that publishes newly created tickets via HTTP
to the Kafka topic so worker agents can consume them.
"""
import json
import asyncio
from typing import Optional

from aiokafka import AIOKafkaProducer
from structlog import get_logger

from ..config import get_settings


class KafkaTicketProducer:
    """
    Kafka producer for publishing tickets to execution.tickets topic.

    This bridges the gap between HTTP ticket creation (Orchestrator → HTTP)
    and Kafka ticket consumption (Worker Agents ← Kafka).
    """

    def __init__(self):
        self._producer: Optional[AIOKafkaProducer] = None
        self._settings = get_settings()
        self._logger = get_logger(__name__)
        self._topic = self._settings.kafka_tickets_topic  # 'execution.tickets'

    async def start(self, max_retries: int = 5, initial_delay: float = 1.0):
        """
        Initialize and start the Kafka producer.

        Args:
            max_retries: Maximum number of connection attempts
            initial_delay: Initial delay between retries (seconds)
        """
        self._logger.info(
            "starting_kafka_producer",
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            topic=self._topic
        )

        producer_config = {
            'bootstrap_servers': self._settings.kafka_bootstrap_servers,
            'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
            'key_serializer': lambda k: k.encode('utf-8') if k else None,
            'acks': 'all',  # Wait for all replicas
            'compression_type': 'snappy',  # Compress messages
            'linger_ms': 10,  # Batch up to 10ms for efficiency
            'max_request_size': 1048576,  # 1MB max request size
        }

        # Add SASL if configured
        if self._settings.kafka_security_protocol != 'PLAINTEXT':
            producer_config.update({
                'security_protocol': self._settings.kafka_security_protocol,
                'sasl_mechanism': self._settings.kafka_sasl_mechanism,
                'sasl_plain_username': self._settings.kafka_sasl_username,
                'sasl_plain_password': self._settings.kafka_sasl_password,
            })

        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                self._producer = AIOKafkaProducer(**producer_config)
                await self._producer.start()
                self._logger.info(
                    "kafka_producer_started",
                    bootstrap_servers=self._settings.kafka_bootstrap_servers,
                    topic=self._topic
                )
                return

            except Exception as e:
                last_error = e
                retry_count += 1
                self._logger.warning(
                    "kafka_producer_start_failed",
                    error=str(e),
                    retry_count=retry_count,
                    max_retries=max_retries,
                    attempt=f"{retry_count}/{max_retries}"
                )
                if retry_count < max_retries:
                    await asyncio.sleep(initial_delay * (2 ** (retry_count - 1)))

        # If we get here, all retries failed
        self._logger.error(
            "kafka_producer_start_failed_all_retries",
            error=str(last_error),
            max_retries=max_retries
        )
        raise RuntimeError(f"Failed to start Kafka producer after {max_retries} attempts: {last_error}")

    async def stop(self):
        """Stop the Kafka producer gracefully."""
        if self._producer:
            self._logger.info("stopping_kafka_producer")
            await self._producer.stop()
            self._logger.info("kafka_producer_stopped")
        self._producer = None

    async def publish_ticket(
        self,
        ticket: dict,
        key: Optional[str] = None,
        timeout_ms: int = 5000
    ) -> bool:
        """
        Publish ticket to Kafka topic.

        Args:
            ticket: Ticket data as dictionary
            key: Optional key for partitioning (default: ticket_id)
            timeout_ms: Timeout for publish operation

        Returns:
            True if published successfully, False otherwise
        """
        if not self._producer:
            self._logger.warning("kafka_producer_not_initialized", ticket_id=ticket.get('ticket_id'))
            return False

        # Use ticket_id as key for consistent partitioning
        if key is None:
            key = ticket.get('ticket_id')

        try:
            await asyncio.wait_for(
                self._producer.send_and_wait(
                    self._topic,
                    value=ticket,
                    key=key
                ),
                timeout=timeout_ms / 1000.0
            )

            self._logger.info(
                "ticket_published_to_kafka",
                ticket_id=ticket.get('ticket_id'),
                topic=self._topic,
                key=key
            )
            return True

        except asyncio.TimeoutError:
            self._logger.error(
                "ticket_publish_timeout",
                ticket_id=ticket.get('ticket_id'),
                timeout_ms=timeout_ms
            )
            return False

        except Exception as e:
            self._logger.error(
                "ticket_publish_failed",
                ticket_id=ticket.get('ticket_id'),
                error=str(e),
                error_type=type(e).__name__
            )
            return False

    async def health_check(self) -> bool:
        """
        Check if producer is healthy and can connect to Kafka.

        Returns:
            True if healthy, False otherwise
        """
        if not self._producer:
            return False

        # Check if producer is in a valid state
        # (simple check - producer is running if not None)
        return True


# Global producer instance
_producer: Optional[KafkaTicketProducer] = None


async def get_kafka_producer() -> KafkaTicketProducer:
    """
    Get or create the global Kafka producer instance.

    Returns:
        KafkaTicketProducer instance

    Raises:
        RuntimeError: If producer failed to initialize
    """
    global _producer

    if _producer is None:
        _producer = KafkaTicketProducer()
        await _producer.start()

    return _producer


async def close_kafka_producer():
    """Close the global Kafka producer instance."""
    global _producer

    if _producer:
        await _producer.stop()
        _producer = None
