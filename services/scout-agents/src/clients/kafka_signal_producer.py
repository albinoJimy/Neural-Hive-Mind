"""Kafka producer for publishing Scout Signals"""
import asyncio
import json
from typing import List, Optional
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
import structlog

from ..models.scout_signal import ScoutSignal
from ..config import get_settings

logger = structlog.get_logger()


class KafkaSignalProducer:
    """Produces Scout Signals to Kafka topics"""

    def __init__(self):
        self.settings = get_settings()
        self.producer: Optional[AIOKafkaProducer] = None
        self._is_running = False

    async def start(self):
        """Initialize and start Kafka producer"""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.kafka.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                compression_type='snappy',
                acks='all',
                retries=3,
                max_in_flight_requests_per_connection=5,
                enable_idempotence=True
            )

            await self.producer.start()
            self._is_running = True
            logger.info(
                "kafka_producer_started",
                bootstrap_servers=self.settings.kafka.bootstrap_servers
            )
        except Exception as e:
            logger.error("kafka_producer_start_failed", error=str(e))
            raise

    async def stop(self):
        """Stop Kafka producer gracefully"""
        if self.producer:
            try:
                await self.producer.stop()
                self._is_running = False
                logger.info("kafka_producer_stopped")
            except Exception as e:
                logger.error("kafka_producer_stop_failed", error=str(e))

    async def publish_signal(self, signal: ScoutSignal) -> bool:
        """
        Publish a Scout Signal to exploration.signals topic

        Args:
            signal: ScoutSignal instance

        Returns:
            bool: True if published successfully
        """
        if not self.producer or not self._is_running:
            logger.error("kafka_producer_not_running")
            return False

        try:
            # Convert to Avro-compatible dict
            signal_dict = signal.to_avro_dict()

            # Partition by exploration domain for better distribution
            partition_key = signal.exploration_domain.value.encode('utf-8')

            # Send message
            future = await self.producer.send(
                self.settings.kafka.topics_signals,
                value=signal_dict,
                key=partition_key
            )

            # Wait for acknowledgment
            record_metadata = await future

            logger.info(
                "signal_published_to_kafka",
                signal_id=signal.signal_id,
                signal_type=signal.signal_type.value,
                domain=signal.exploration_domain.value,
                topic=record_metadata.topic,
                partition=record_metadata.partition,
                offset=record_metadata.offset
            )

            return True

        except KafkaError as e:
            logger.error(
                "kafka_publish_failed",
                signal_id=signal.signal_id,
                error=str(e),
                error_type="kafka_error"
            )
            return False
        except Exception as e:
            logger.error(
                "signal_publish_failed",
                signal_id=signal.signal_id,
                error=str(e),
                error_type=type(e).__name__
            )
            return False

    async def publish_opportunity(self, signal: ScoutSignal) -> bool:
        """
        Publish validated opportunity to exploration.opportunities topic

        Args:
            signal: Validated ScoutSignal instance

        Returns:
            bool: True if published successfully
        """
        if not self.producer or not self._is_running:
            logger.error("kafka_producer_not_running")
            return False

        try:
            signal_dict = signal.to_avro_dict()
            partition_key = signal.exploration_domain.value.encode('utf-8')

            future = await self.producer.send(
                self.settings.kafka.topics_opportunities,
                value=signal_dict,
                key=partition_key
            )

            record_metadata = await future

            logger.info(
                "opportunity_published_to_kafka",
                signal_id=signal.signal_id,
                domain=signal.exploration_domain.value,
                topic=record_metadata.topic,
                partition=record_metadata.partition,
                offset=record_metadata.offset
            )

            return True

        except Exception as e:
            logger.error(
                "opportunity_publish_failed",
                signal_id=signal.signal_id,
                error=str(e)
            )
            return False

    async def publish_batch(self, signals: List[ScoutSignal]) -> int:
        """
        Publish multiple signals in batch

        Args:
            signals: List of ScoutSignal instances

        Returns:
            int: Number of successfully published signals
        """
        if not signals:
            return 0

        success_count = 0
        tasks = [self.publish_signal(signal) for signal in signals]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if result is True:
                success_count += 1

        logger.info(
            "batch_publish_completed",
            total_signals=len(signals),
            successful=success_count,
            failed=len(signals) - success_count
        )

        return success_count
