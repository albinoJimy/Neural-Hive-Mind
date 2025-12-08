"""
Kafka consumer for Flow C integration in Orchestrator Dynamic.

Consumes consolidated decisions from plans.consensus and executes Flow C.

NOTA: Este módulo agora suporta configuração dinâmica via OrchestratorSettings.
Os defaults são mantidos para compatibilidade, mas devem ser substituídos
por config injetada em produção.
"""

import asyncio
import time
import structlog
import json
import os
import io
from typing import Optional
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from opentelemetry import trace
from prometheus_client import Counter

# Avro support
try:
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroDeserializer
    import fastavro
    AVRO_AVAILABLE = True
except ImportError:
    AVRO_AVAILABLE = False

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


def _deserialize_avro_message(raw_bytes: bytes, schema_registry_url: str = None) -> dict:
    """
    Deserialize Avro message with Confluent wire format.

    Confluent wire format:
    - Byte 0: Magic byte (0x00)
    - Bytes 1-4: Schema ID (big-endian int)
    - Bytes 5+: Avro payload
    """
    if len(raw_bytes) < 5:
        # Too short for Avro wire format, try JSON
        return json.loads(raw_bytes.decode('utf-8'))

    magic_byte = raw_bytes[0]
    if magic_byte != 0:
        # Not Avro wire format, try JSON
        return json.loads(raw_bytes.decode('utf-8'))

    # Extract schema ID and Avro payload
    schema_id = int.from_bytes(raw_bytes[1:5], byteorder='big')
    avro_payload = raw_bytes[5:]

    # Use fastavro to deserialize without schema (schemaless reader)
    # The schema is embedded or we use a generic approach
    if AVRO_AVAILABLE:
        try:
            reader = io.BytesIO(avro_payload)
            # Read single record using fastavro's schemaless reader
            records = list(fastavro.reader(reader))
            if records:
                return records[0]
        except Exception as e:
            # Fallback: try with schema from registry
            if schema_registry_url:
                try:
                    client = SchemaRegistryClient({'url': schema_registry_url})
                    schema = client.get_schema(schema_id)
                    parsed_schema = fastavro.parse_schema(json.loads(schema.schema_str))
                    reader = io.BytesIO(avro_payload)
                    return fastavro.schemaless_reader(reader, parsed_schema)
                except Exception as registry_error:
                    logger.warning("schema_registry_fallback_failed", error=str(registry_error))
            raise e

    raise ValueError("Avro deserialization not available")


class FlowCConsumer:
    """Kafka consumer for Flow C orchestration."""

    def __init__(
        self,
        config=None,  # OrchestratorSettings - preferido
        kafka_bootstrap_servers: Optional[str] = None,
        input_topic: Optional[str] = None,
        incident_topic: Optional[str] = None,
        group_id: Optional[str] = None,
    ):
        """
        Initialize FlowCConsumer.

        Args:
            config: OrchestratorSettings object (preferido)
            kafka_bootstrap_servers: Override para bootstrap servers
            input_topic: Override para tópico de entrada
            incident_topic: Override para tópico de incidentes
            group_id: Override para consumer group ID
        """
        # Usar config fornecido ou fallback para defaults
        if config:
            self.kafka_servers = kafka_bootstrap_servers or config.kafka_bootstrap_servers
            self.input_topic = input_topic or config.kafka_consensus_topic
            self.incident_topic = incident_topic or config.ml_allocation_outcomes_topic
            self.group_id = group_id or f"{config.kafka_consumer_group_id}-flow-c"
            self.config = config
        else:
            # Fallback para defaults (deprecated - apenas para testes)
            self.kafka_servers = kafka_bootstrap_servers or "kafka-bootstrap.kafka.svc.cluster.local:9092"
            self.input_topic = input_topic or "plans.consensus"
            self.incident_topic = incident_topic or "orchestration.incidents"
            self.group_id = group_id or "flow-c-orchestrator"
            self.config = None

        self.consumer: AIOKafkaConsumer = None
        self.producer: AIOKafkaProducer = None
        self.orchestrator: FlowCOrchestrator = None
        self.running = False
        self.schema_registry_url = os.getenv(
            'SCHEMA_REGISTRY_URL',
            'http://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v6'
        )
        self.logger = logger.bind(service="flow_c_consumer")

    async def start(self):
        """Initialize and start consumer."""
        self.logger.info(
            "starting_flow_c_consumer",
            bootstrap_servers=self.kafka_servers,
            input_topic=self.input_topic,
            group_id=self.group_id,
        )

        # Construir config do consumer
        # NOTA: Não usar value_deserializer - vamos deserializar manualmente
        # para suportar tanto Avro (Confluent wire format) quanto JSON
        consumer_config = {
            'bootstrap_servers': self.kafka_servers,
            'group_id': self.group_id,
            'auto_offset_reset': 'earliest',
            'enable_auto_commit': False,
            # Não definir value_deserializer - recebemos bytes crus
        }

        # Adicionar SASL se configurado
        if self.config and self.config.kafka_security_protocol != 'PLAINTEXT':
            consumer_config.update({
                'security_protocol': self.config.kafka_security_protocol,
                'sasl_mechanism': 'PLAIN',
                'sasl_plain_username': self.config.kafka_sasl_username,
                'sasl_plain_password': self.config.kafka_sasl_password,
            })

        # Initialize consumer
        self.consumer = AIOKafkaConsumer(self.input_topic, **consumer_config)
        await self.consumer.start()

        # Construir config do producer
        producer_config = {
            'bootstrap_servers': self.kafka_servers,
            'value_serializer': lambda v: json.dumps(v).encode(),
        }

        # Adicionar SASL se configurado
        if self.config and self.config.kafka_security_protocol != 'PLAINTEXT':
            producer_config.update({
                'security_protocol': self.config.kafka_security_protocol,
                'sasl_mechanism': 'PLAIN',
                'sasl_plain_username': self.config.kafka_sasl_username,
                'sasl_plain_password': self.config.kafka_sasl_password,
            })

        # Initialize producer for incidents
        self.producer = AIOKafkaProducer(**producer_config)
        await self.producer.start()

        # Initialize orchestrator
        self.orchestrator = FlowCOrchestrator()
        await self.orchestrator.initialize()

        self.running = True
        self.logger.info("flow_c_consumer_started", group_id=self.group_id)

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
        consolidated_decision = None

        try:
            # Deserializar mensagem (suporta Avro e JSON)
            raw_value = message.value
            if isinstance(raw_value, bytes):
                try:
                    consolidated_decision = _deserialize_avro_message(
                        raw_value,
                        self.schema_registry_url
                    )
                except Exception as deser_err:
                    self.logger.warning(
                        "avro_deserialization_failed_trying_json",
                        error=str(deser_err)
                    )
                    # Fallback para JSON
                    consolidated_decision = json.loads(raw_value.decode('utf-8'))
            else:
                consolidated_decision = raw_value

            # Parse cognitive_plan se for string JSON (serializado pelo Avro)
            cognitive_plan = consolidated_decision.get("cognitive_plan")
            if isinstance(cognitive_plan, str):
                try:
                    consolidated_decision["cognitive_plan"] = json.loads(cognitive_plan)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid cognitive_plan JSON: {e}"
                    ) from e

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
            safe_decision = consolidated_decision or self._coerce_decision_dict(message.value)
            await self._publish_incident(safe_decision, str(e))

    async def _publish_incident(self, decision: dict, error: str):
        """Publish incident to orchestration.incidents topic."""
        decision = self._coerce_decision_dict(decision)

        incident = {
            "incident_type": "flow_c_failure",
            "intent_id": decision.get("intent_id"),
            "plan_id": decision.get("plan_id"),
            "decision_id": decision.get("decision_id"),
            "error": error,
            "timestamp": time.time(),  # Python 3.10+: asyncio.get_event_loop() deprecated
        }

        await self.producer.send_and_wait(self.incident_topic, value=incident)
        self.logger.warning("incident_published", incident_type="flow_c_failure")

    def _coerce_decision_dict(self, value) -> dict:
        """Best effort to ensure incident payload is a dict with context."""
        if isinstance(value, dict):
            return value
        if isinstance(value, bytes):
            try:
                return _deserialize_avro_message(value, self.schema_registry_url)
            except Exception as deser_err:
                try:
                    return json.loads(value.decode('utf-8'))
                except Exception as json_err:
                    return {
                        "raw_decision": value.decode('utf-8', errors='ignore'),
                        "deserialization_error": str(deser_err),
                        "json_error": str(json_err),
                    }
        return {"raw_decision": str(value)}
