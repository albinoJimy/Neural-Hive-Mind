"""
Flow C telemetry publisher for event tracking and correlation.
"""

import structlog
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from aiokafka import AIOKafkaProducer
from opentelemetry import trace
from prometheus_client import Counter, Gauge
import redis.asyncio as aioredis

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)

# Metrics
telemetry_published = Counter(
    "neural_hive_flow_c_telemetry_published_total",
    "Total telemetry events published",
    ["step"],
)
telemetry_buffer_size = Gauge(
    "neural_hive_flow_c_telemetry_buffer_size",
    "Current telemetry buffer size",
)


class FlowCTelemetryPublisher:
    """Publisher for Flow C telemetry events."""

    def __init__(
        self,
        kafka_bootstrap_servers: str = "neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092",
        topic: str = "telemetry-flow-c",
        redis_url: str = "redis://redis-cluster.redis-cluster.svc.cluster.local:6379",
        buffer_ttl: int = 3600,  # 1 hour
    ):
        self.kafka_servers = kafka_bootstrap_servers
        self.topic = topic
        self.redis_url = redis_url
        self.buffer_ttl = buffer_ttl
        self.producer: Optional[AIOKafkaProducer] = None
        self.redis: Optional[aioredis.Redis] = None
        self.logger = logger.bind(service="flow_c_telemetry")

    async def initialize(self):
        """Initialize Kafka producer and Redis buffer."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await self.producer.start()

        self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
        self.logger.info("telemetry_publisher_initialized")

    async def close(self):
        """Close Kafka producer and Redis connection."""
        if self.producer:
            await self.producer.stop()
        if self.redis:
            await self.redis.close()

    @tracer.start_as_current_span("telemetry.publish_event")
    async def publish_event(
        self,
        event_type: str,
        step: str,
        intent_id: str,
        plan_id: str,
        decision_id: str,
        workflow_id: str,
        ticket_ids: List[str],
        duration_ms: int,
        status: str,
        metadata: Dict[str, Any],
    ) -> None:
        """
        Publish Flow C telemetry event.

        Args:
            event_type: Event type (step_started, step_completed, step_failed)
            step: Flow C step (C1-C6)
            intent_id: Intent identifier
            plan_id: Plan identifier
            decision_id: Decision identifier
            workflow_id: Workflow identifier
            ticket_ids: List of ticket IDs
            duration_ms: Step duration in milliseconds
            status: Step status
            metadata: Additional metadata
        """
        # Get OpenTelemetry context
        span = trace.get_current_span()
        trace_id = format(span.get_span_context().trace_id, '032x')
        span_id = format(span.get_span_context().span_id, '016x')

        event = {
            "event_type": event_type,
            "step": step,
            "intent_id": intent_id,
            "plan_id": plan_id,
            "decision_id": decision_id,
            "workflow_id": workflow_id,
            "ticket_ids": ticket_ids,
            "timestamp": datetime.utcnow().isoformat(),
            "duration_ms": duration_ms,
            "status": status,
            "trace_id": trace_id,
            "span_id": span_id,
            "metadata": metadata,
        }

        try:
            await self.producer.send_and_wait(self.topic, value=event)
            telemetry_published.labels(step=step).inc()
            self.logger.info(
                "telemetry_published",
                step=step,
                event_type=event_type,
                intent_id=intent_id,
            )
        except Exception as e:
            self.logger.error("telemetry_publish_failed", error=str(e))
            # Buffer to Redis on failure
            await self._buffer_event(event)

    async def _buffer_event(self, event: Dict[str, Any]):
        """Buffer event to Redis if Kafka is unavailable."""
        if not self.redis:
            return

        buffer_key = f"telemetry:buffer:{event['intent_id']}"
        await self.redis.lpush(buffer_key, json.dumps(event))
        await self.redis.expire(buffer_key, self.buffer_ttl)

        # Incrementar Gauge
        telemetry_buffer_size.inc()

        self.logger.warning("event_buffered", buffer_key=buffer_key)

    async def flush_buffer(self, intent_id: str):
        """Flush buffered events for intent."""
        if not self.redis:
            return

        buffer_key = f"telemetry:buffer:{intent_id}"
        while True:
            event_json = await self.redis.rpop(buffer_key)
            if not event_json:
                break

            event = json.loads(event_json)
            try:
                await self.producer.send_and_wait(self.topic, value=event)
                # Decrementar Gauge após flush bem-sucedido
                telemetry_buffer_size.dec()
                self.logger.info("buffered_event_published", intent_id=intent_id)
            except Exception as e:
                self.logger.error("buffer_flush_failed", error=str(e))
                # Re-buffer
                await self.redis.lpush(buffer_key, event_json)
                break
