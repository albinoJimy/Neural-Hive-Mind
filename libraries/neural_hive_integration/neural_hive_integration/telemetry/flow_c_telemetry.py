"""
Flow C telemetry publisher for event tracking and correlation.

Suporta:
- Publicação de eventos para Kafka
- Buffer Redis com fallback para in-memory
- Background flush worker para recuperação automática
- Limite de tamanho do buffer para evitar overflow
"""

import structlog
import json
import asyncio
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
telemetry_buffer_drops = Counter(
    "neural_hive_flow_c_telemetry_buffer_drops_total",
    "Events dropped due to buffer overflow",
)
telemetry_flush_success = Counter(
    "neural_hive_flow_c_telemetry_flush_success_total",
    "Successful buffer flushes",
)


class FlowCTelemetryPublisher:
    """Publisher for Flow C telemetry events with resilient buffering."""

    def __init__(
        self,
        kafka_bootstrap_servers: str = "neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092",
        topic: str = "telemetry-flow-c",
        redis_url: str = "redis://redis-cluster.redis-cluster.svc.cluster.local:6379",
        buffer_ttl: int = 3600,  # 1 hour
        max_buffer_size: int = 10000,
        flush_interval: int = 60,  # segundos
    ):
        self.kafka_servers = kafka_bootstrap_servers
        self.topic = topic
        self.redis_url = redis_url
        self.buffer_ttl = buffer_ttl
        self.max_buffer_size = max_buffer_size
        self.flush_interval = flush_interval
        self.producer: Optional[AIOKafkaProducer] = None
        self.redis: Optional[aioredis.Redis] = None
        self.logger = logger.bind(service="flow_c_telemetry")
        
        # In-memory buffer como fallback final
        self._in_memory_buffer: List[Dict[str, Any]] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    async def initialize(self):
        """Initialize Kafka producer and Redis buffer with fallback handling."""
        # Inicializar Kafka
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.kafka_servers,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self.producer.start()
            self.logger.info("kafka_producer_initialized")
        except Exception as e:
            self.logger.error("kafka_producer_init_failed", error=str(e))
            self.producer = None  # Usará buffer

        # Inicializar Redis
        try:
            self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
            await self.redis.ping()
            self.logger.info("redis_buffer_initialized")
        except Exception as e:
            self.logger.warning(
                "redis_buffer_init_failed",
                error=str(e),
                message="Usando buffer in-memory como fallback"
            )
            self.redis = None

        # Iniciar background flush worker
        self._running = True
        self._flush_task = asyncio.create_task(self._background_flush_worker())

        self.logger.info(
            "telemetry_publisher_initialized",
            kafka_available=self.producer is not None,
            redis_available=self.redis is not None,
        )

    async def close(self):
        """Close Kafka producer and Redis connection."""
        self._running = False
        
        # Cancelar background task
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Tentar flush final antes de fechar
        if self.producer and self._in_memory_buffer:
            for event in self._in_memory_buffer[:]:
                try:
                    await self.producer.send_and_wait(self.topic, value=event)
                    self._in_memory_buffer.remove(event)
                except Exception:
                    break

        if self.producer:
            await self.producer.stop()
        if self.redis:
            await self.redis.close()
            
        self.logger.info(
            "telemetry_publisher_closed",
            unflushed_events=len(self._in_memory_buffer),
        )

    async def _background_flush_worker(self):
        """Background task para flush periódico de eventos bufferizados."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                
                if not self.producer:
                    continue
                    
                # Flush Redis buffer
                if self.redis:
                    try:
                        keys = await self.redis.keys("telemetry:buffer:*")
                        for key in keys:
                            intent_id = key.split(":")[-1]
                            await self.flush_buffer(intent_id)
                    except Exception as e:
                        self.logger.warning("redis_buffer_flush_failed", error=str(e))
                
                # Flush in-memory buffer
                if self._in_memory_buffer:
                    events_to_flush = self._in_memory_buffer.copy()
                    self._in_memory_buffer.clear()
                    
                    for event in events_to_flush:
                        try:
                            await self.producer.send_and_wait(self.topic, value=event)
                            telemetry_buffer_size.dec()
                            telemetry_flush_success.inc()
                        except Exception as e:
                            # Re-buffer em caso de falha
                            if len(self._in_memory_buffer) < self.max_buffer_size:
                                self._in_memory_buffer.append(event)
                            else:
                                telemetry_buffer_drops.inc()
                            self.logger.warning(
                                "in_memory_flush_failed",
                                error=str(e),
                            )
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("background_flush_error", error=str(e))

    @tracer.start_as_current_span("telemetry.publish_flow_started")
    async def publish_flow_started(
        self,
        intent_id: str,
        plan_id: str,
        decision_id: str,
        correlation_id: str,
    ) -> None:
        """Publish FLOW_C_STARTED event."""
        span = trace.get_current_span()
        trace_id = format(span.get_span_context().trace_id, '032x')
        span_id = format(span.get_span_context().span_id, '016x')

        event = {
            "event_type": "FLOW_C_STARTED",
            "timestamp": datetime.utcnow().isoformat(),
            "intent_id": intent_id,
            "plan_id": plan_id,
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "trace_id": trace_id,
            "span_id": span_id,
        }

        try:
            await self.producer.send_and_wait(self.topic, value=event)
            telemetry_published.labels(step="C0").inc()
            self.logger.info("flow_started_published", intent_id=intent_id, plan_id=plan_id)
        except Exception as e:
            self.logger.error("flow_started_publish_failed", error=str(e))
            await self._buffer_event(event)

    @tracer.start_as_current_span("telemetry.publish_ticket_assigned")
    async def publish_ticket_assigned(
        self,
        ticket_id: str,
        task_type: str,
        worker_id: str,
        intent_id: str,
        plan_id: str,
    ) -> None:
        """Publish TICKET_ASSIGNED event."""
        span = trace.get_current_span()
        trace_id = format(span.get_span_context().trace_id, '032x')
        span_id = format(span.get_span_context().span_id, '016x')

        event = {
            "event_type": "TICKET_ASSIGNED",
            "timestamp": datetime.utcnow().isoformat(),
            "ticket_id": ticket_id,
            "task_type": task_type,
            "worker_id": worker_id,
            "intent_id": intent_id,
            "plan_id": plan_id,
            "trace_id": trace_id,
            "span_id": span_id,
        }

        try:
            await self.producer.send_and_wait(self.topic, value=event)
            telemetry_published.labels(step="C4").inc()
            self.logger.info("ticket_assigned_published", ticket_id=ticket_id, worker_id=worker_id)
        except Exception as e:
            self.logger.error("ticket_assigned_publish_failed", error=str(e))
            await self._buffer_event(event)

    @tracer.start_as_current_span("telemetry.publish_ticket_completed")
    async def publish_ticket_completed(
        self,
        ticket_id: str,
        task_type: str,
        worker_id: str,
        intent_id: str,
        plan_id: str,
        result: dict,
    ) -> None:
        """Publish TICKET_COMPLETED event."""
        span = trace.get_current_span()
        trace_id = format(span.get_span_context().trace_id, '032x')
        span_id = format(span.get_span_context().span_id, '016x')

        event = {
            "event_type": "TICKET_COMPLETED",
            "timestamp": datetime.utcnow().isoformat(),
            "ticket_id": ticket_id,
            "task_type": task_type,
            "worker_id": worker_id,
            "intent_id": intent_id,
            "plan_id": plan_id,
            "result": result,
            "trace_id": trace_id,
            "span_id": span_id,
        }

        try:
            await self.producer.send_and_wait(self.topic, value=event)
            telemetry_published.labels(step="C5").inc()
            self.logger.info("ticket_completed_published", ticket_id=ticket_id, worker_id=worker_id)
        except Exception as e:
            self.logger.error("ticket_completed_publish_failed", error=str(e))
            await self._buffer_event(event)

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
        """
        Buffer event to Redis or in-memory if Kafka is unavailable.
        
        Hierarchy:
        1. Redis buffer (preferido)
        2. In-memory buffer (fallback)
        3. Drop event (se ambos buffers estão cheios)
        """
        # Tentar Redis primeiro
        if self.redis:
            try:
                buffer_key = f"telemetry:buffer:{event['intent_id']}"
                
                # Verificar tamanho do buffer
                buffer_size = await self.redis.llen(buffer_key)
                if buffer_size >= self.max_buffer_size:
                    # Remover evento mais antigo para fazer espaço
                    await self.redis.rpop(buffer_key)
                    self.logger.warning(
                        "buffer_full_dropping_oldest",
                        buffer_key=buffer_key,
                        buffer_size=buffer_size,
                    )
                
                await self.redis.lpush(buffer_key, json.dumps(event))
                await self.redis.expire(buffer_key, self.buffer_ttl)
                telemetry_buffer_size.inc()
                
                self.logger.debug("event_buffered_redis", buffer_key=buffer_key)
                return
            except Exception as e:
                self.logger.warning("redis_buffer_failed", error=str(e))

        # Fallback para in-memory buffer
        if len(self._in_memory_buffer) < self.max_buffer_size:
            self._in_memory_buffer.append(event)
            telemetry_buffer_size.inc()
            self.logger.warning(
                "event_buffered_in_memory",
                events_buffered=len(self._in_memory_buffer),
            )
        else:
            # Buffer cheio - dropar evento
            telemetry_buffer_drops.inc()
            self.logger.error(
                "buffer_full_event_dropped",
                intent_id=event.get('intent_id'),
                event_type=event.get('event_type'),
            )

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
