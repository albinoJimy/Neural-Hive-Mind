"""Main exploration engine orchestrating the scout pipeline"""
import asyncio
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Deque
import structlog
from neural_hive_observability import get_tracer, instrument_kafka_producer

from ..models.raw_event import RawEvent
from ..models.scout_signal import ScoutSignal, ChannelType
from neural_hive_domain import UnifiedDomain
from ..detection.signal_detector import SignalDetector
from ..clients.kafka_signal_producer import KafkaSignalProducer
from ..clients.memory_layer_client import MemoryLayerClient
from ..clients.pheromone_client import PheromoneClient
from ..config import get_settings

logger = structlog.get_logger()


class ExplorationEngine:
    """Main engine for Scout Agent exploration pipeline"""

    def __init__(self, scout_agent_id: str):
        self.scout_agent_id = scout_agent_id
        self.settings = get_settings()

        # Core components
        self.detector = SignalDetector(scout_agent_id)
        self.kafka_producer = KafkaSignalProducer()
        self.memory_client = MemoryLayerClient()
        self.pheromone_client = PheromoneClient()

        # Internal queue for backpressure
        self.signal_queue: Deque[ScoutSignal] = deque(maxlen=1000)

        # Rate limiting
        self.published_signals: Deque[datetime] = deque()
        self.max_signals_per_minute = self.settings.detection.max_signals_per_minute

        # State
        self._is_running = False

        # Statistics
        self.stats = {
            'processed': 0,
            'detected': 0,
            'published': 0,
            'discarded': 0,
            'rate_limited': 0
        }

    async def start(self):
        """Initialize and start the exploration engine"""
        try:
            await self.kafka_producer.start()
            self.kafka_producer = instrument_kafka_producer(self.kafka_producer)
            await self.memory_client.start()
            await self.pheromone_client.start()
            self._is_running = True

            logger.info(
                "exploration_engine_started",
                scout_agent_id=self.scout_agent_id,
                max_signals_per_minute=self.max_signals_per_minute
            )
        except Exception as e:
            logger.error("exploration_engine_start_failed", error=str(e))
            raise

    async def stop(self):
        """Stop the exploration engine gracefully"""
        self._is_running = False

        # Process remaining signals in queue
        logger.info(
            "processing_remaining_signals",
            queue_size=len(self.signal_queue)
        )

        while self.signal_queue:
            signal = self.signal_queue.popleft()
            await self._publish_signal_internal(signal)

        await self.kafka_producer.stop()
        await self.memory_client.stop()
        await self.pheromone_client.stop()

        logger.info(
            "exploration_engine_stopped",
            stats=self.stats
        )

    async def process_event(
        self,
        event: RawEvent,
        domain: UnifiedDomain,
        channel: ChannelType = ChannelType.CORE
    ) -> Optional[ScoutSignal]:
        """
        Main pipeline: process raw event and publish signal if detected

        Args:
            event: Raw event to process
            domain: Exploration domain
            channel: Channel type

        Returns:
            ScoutSignal if detected and published, None otherwise
        """
        if not self._is_running:
            logger.warning("engine_not_running", event_id=event.event_id)
            return None

        self.stats['processed'] += 1

        try:
            # Step 1: Detect signal
            tracer = get_tracer()
            with tracer.start_as_current_span("signal_detection") as span:
                span.set_attribute("neural.hive.agent_id", self.scout_agent_id)
                signal = await self.detector.detect(event, domain, channel)
                if signal:
                    span.set_attribute("neural.hive.signal_type", signal.signal_type.value)
                    span.set_attribute("neural.hive.curiosity_score", signal.curiosity_score)

            if not signal:
                return None

            self.stats['detected'] += 1

            # Step 2: Check rate limit
            if not self._check_rate_limit():
                self.stats['rate_limited'] += 1
                logger.warning(
                    "rate_limit_exceeded",
                    signal_id=signal.signal_id,
                    current_rate=len(self.published_signals)
                )

                # Add to queue if high priority
                if signal.calculate_priority() > 0.7:
                    self.signal_queue.append(signal)

                return None

            # Step 3: Publish signal
            success = await self._publish_signal_internal(signal)

            if success:
                self.stats['published'] += 1
                return signal
            else:
                self.stats['discarded'] += 1
                return None

        except Exception as e:
            logger.error(
                "event_processing_failed",
                event_id=event.event_id,
                error=str(e)
            )
            return None

    def _check_rate_limit(self) -> bool:
        """Check if rate limit allows publishing new signal"""
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=1)

        # Remove old timestamps
        while self.published_signals and self.published_signals[0] < cutoff:
            self.published_signals.popleft()

        # Check current rate
        return len(self.published_signals) < self.max_signals_per_minute

    async def _publish_signal_internal(self, signal: ScoutSignal) -> bool:
        """Internal method to publish signal to all destinations"""
        try:
            # Publish to Kafka
            kafka_success = await self.kafka_producer.publish_signal(signal)

            if not kafka_success:
                logger.error(
                    "kafka_publish_failed",
                    signal_id=signal.signal_id
                )
                return False

            # Store in Memory Layer (Redis for short-term)
            memory_success = await self.memory_client.store_signal_redis(signal)

            if not memory_success:
                logger.warning(
                    "memory_storage_failed",
                    signal_id=signal.signal_id
                )
                # Don't fail the whole pipeline if memory storage fails

            # Publish digital pheromone
            pheromone_success = await self.pheromone_client.publish_pheromone(signal)

            if not pheromone_success:
                logger.warning(
                    "pheromone_publish_failed",
                    signal_id=signal.signal_id
                )
                # Don't fail the whole pipeline if pheromone publish fails

            # Update rate limit tracker
            self.published_signals.append(datetime.utcnow())

            logger.info(
                "signal_published",
                signal_id=signal.signal_id,
                signal_type=signal.signal_type.value,
                domain=signal.exploration_domain.value,
                curiosity=signal.curiosity_score,
                confidence=signal.confidence
            )

            return True

        except Exception as e:
            logger.error(
                "signal_publish_failed",
                signal_id=signal.signal_id,
                error=str(e)
            )
            return False

    async def process_queue(self):
        """Process signals from internal queue (for rate-limited signals)"""
        if not self.signal_queue:
            return

        # Sort queue by priority
        sorted_signals = sorted(
            self.signal_queue,
            key=lambda s: s.calculate_priority(),
            reverse=True
        )

        processed = 0
        for signal in sorted_signals:
            if not self._check_rate_limit():
                break

            success = await self._publish_signal_internal(signal)
            if success:
                processed += 1
                self.stats['published'] += 1

        # Remove processed signals from queue
        for _ in range(processed):
            if self.signal_queue:
                self.signal_queue.popleft()

        if processed > 0:
            logger.info(
                "queue_processed",
                processed=processed,
                remaining=len(self.signal_queue)
            )

    def get_stats(self) -> dict:
        """Get engine statistics"""
        return {
            **self.stats,
            'queue_size': len(self.signal_queue),
            'current_rate': len(self.published_signals),
            'is_running': self._is_running
        }

    async def handle_feedback(self, signal_id: str, validation_score: float):
        """
        Handle feedback from Analyst Agents for adaptive learning

        Args:
            signal_id: Signal identifier
            validation_score: Validation score (0-1)
        """
        try:
            # Update Bayesian filter priors
            # Note: This requires tracking signal-to-domain mapping
            # For MVP, we'll use a simplified approach

            logger.info(
                "feedback_received",
                signal_id=signal_id,
                validation_score=validation_score
            )

            # TODO: Implement adaptive learning based on feedback

        except Exception as e:
            logger.error(
                "feedback_handling_failed",
                signal_id=signal_id,
                error=str(e)
            )
