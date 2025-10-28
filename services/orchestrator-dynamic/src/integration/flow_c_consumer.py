"""
Kafka consumer for Flow C integration in Orchestrator Dynamic.

Consumes consolidated decisions from plans.consensus and executes Flow C.
"""

import asyncio
import structlog
import json
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from opentelemetry import trace
from prometheus_client import Counter

from neural_hive_integration.orchestration.flow_c_orchestrator import FlowCOrchestrator

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)

# Metrics
messages_consumed = Counter(
    "neural_hive_flow_c_consumer_messages_total",
    "Total messages consumed from plans.consensus",
)
consumer_errors = Counter(
    "neural_hive_flow_c_consumer_errors_total",
    "Total consumer errors",
    ["error_type"],
)
consumer_lag = Counter(
    "neural_hive_flow_c_consumer_lag",
    "Consumer lag",
)


class FlowCConsumer:
    """Kafka consumer for Flow C orchestration."""

    def __init__(
        self,
        kafka_bootstrap_servers: str = "kafka.neural-hive-messaging:9092",
        input_topic: str = "plans.consensus",
        incident_topic: str = "orchestration.incidents",
        group_id: str = "flow-c-orchestrator",
    ):
        self.kafka_servers = kafka_bootstrap_servers
        self.input_topic = input_topic
        self.incident_topic = incident_topic
        self.group_id = group_id
        self.consumer: AIOKafkaConsumer = None
        self.producer: AIOKafkaProducer = None
        self.orchestrator: FlowCOrchestrator = None
        self.running = False
        self.logger = logger.bind(service="flow_c_consumer")

    async def start(self):
        """Initialize and start consumer."""
        self.logger.info("starting_flow_c_consumer")

        # Initialize consumer with transactional support
        self.consumer = AIOKafkaConsumer(
            self.input_topic,
            bootstrap_servers=self.kafka_servers,
            group_id=self.group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode()),
        )
        await self.consumer.start()

        # Initialize producer for incidents
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await self.producer.start()

        # Initialize orchestrator
        self.orchestrator = FlowCOrchestrator()
        await self.orchestrator.initialize()

        self.running = True
        self.logger.info("flow_c_consumer_started")

    async def stop(self):
        """Stop consumer gracefully."""
        self.logger.info("stopping_flow_c_consumer")
        self.running = False

        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        if self.orchestrator:
            await self.orchestrator.close()

        self.logger.info("flow_c_consumer_stopped")

    async def consume(self):
        """Main consumption loop."""
        while self.running:
            try:
                # Fetch messages
                data = await self.consumer.getmany(timeout_ms=1000, max_records=10)

                for tp, messages in data.items():
                    for message in messages:
                        await self._process_message(message)

                        # Commit offset after successful processing
                        await self.consumer.commit()

            except Exception as e:
                consumer_errors.labels(error_type="consumption").inc()
                self.logger.error("consumption_error", error=str(e))
                await asyncio.sleep(5)

    @tracer.start_as_current_span("flow_c_consumer.process_message")
    async def _process_message(self, message):
        """Process single consolidated decision message."""
        messages_consumed.inc()

        try:
            consolidated_decision = message.value

            self.logger.info(
                "processing_consolidated_decision",
                intent_id=consolidated_decision.get("intent_id"),
                plan_id=consolidated_decision.get("plan_id"),
                decision_id=consolidated_decision.get("decision_id"),
            )

            # Execute Flow C
            result = await self.orchestrator.execute_flow_c(consolidated_decision)

            if not result.success:
                # Publish incident if failed
                await self._publish_incident(consolidated_decision, result.error)

            self.logger.info(
                "flow_c_executed",
                success=result.success,
                duration_ms=result.total_duration_ms,
            )

        except Exception as e:
            consumer_errors.labels(error_type="processing").inc()
            self.logger.error("message_processing_error", error=str(e))

            # Publish incident
            await self._publish_incident(message.value, str(e))

    async def _publish_incident(self, decision: dict, error: str):
        """Publish incident to orchestration.incidents topic."""
        incident = {
            "incident_type": "flow_c_failure",
            "intent_id": decision.get("intent_id"),
            "plan_id": decision.get("plan_id"),
            "decision_id": decision.get("decision_id"),
            "error": error,
            "timestamp": asyncio.get_event_loop().time(),
        }

        await self.producer.send_and_wait(self.incident_topic, value=incident)
        self.logger.warning("incident_published", incident_type="flow_c_failure")
