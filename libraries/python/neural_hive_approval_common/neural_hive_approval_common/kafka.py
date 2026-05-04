"""
Approval Kafka Producer.

Centralized Kafka producer for approval events.

R-A3: Kafka integration (plan_approvals, plan_approvals_responses topics)
INV-4: Kafka topic contracts must remain compatible.
"""

import json
import os
from typing import Any, Optional

import structlog
from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import SerializationContext

from .models import ApprovalResponse

logger = structlog.get_logger()

# Schema Avro para ApprovalResponse
# INV-4: Kafka message format must remain compatible
APPROVAL_RESPONSE_SCHEMA = """
{
  "type": "record",
  "name": "ApprovalResponse",
  "namespace": "com.neuralhive.approval",
  "fields": [
    {"name": "plan_id", "type": "string"},
    {"name": "intent_id", "type": "string"},
    {"name": "decision", "type": {"type": "enum", "name": "Decision", "symbols": ["approved", "rejected"]}},
    {"name": "approved_by", "type": "string"},
    {"name": "approved_at", "type": "long"},
    {"name": "rejection_reason", "type": ["null", "string"], "default": null},
    {"name": "cognitive_plan_json", "type": ["null", "string"], "default": null, "doc": "JSON-serialized cognitive plan"}
  ]
}
"""


class ApprovalKafkaProducerSettings:
    """Settings for ApprovalKafkaProducer."""

    def __init__(
        self,
        bootstrap_servers: str,
        approval_responses_topic: str = "plan_approvals_responses",
        schema_registry_url: Optional[str] = None,
        security_protocol: str = "PLAINTEXT",
        sasl_mechanism: Optional[str] = None,
        sasl_username: Optional[str] = None,
        sasl_password: Optional[str] = None,
        enable_idempotence: bool = True,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.approval_responses_topic = approval_responses_topic
        self.schema_registry_url = schema_registry_url
        self.security_protocol = security_protocol
        self.sasl_mechanism = sasl_mechanism
        self.sasl_username = sasl_username
        self.sasl_password = sasl_password
        self.enable_idempotence = enable_idempotence


class ApprovalKafkaProducer:
    """
    Kafka producer for approval responses.

    R-A3: Publishes to plan_approvals_responses topic.
    INV-4: Maintains Kafka topic contract.
    """

    def __init__(
        self,
        settings: ApprovalKafkaProducerSettings,
    ):
        """
        Initialize Kafka producer.

        Args:
            settings: Producer configuration settings
        """
        self.settings = settings
        self.producer: Optional[Producer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_serializer: Optional[AvroSerializer] = None
        self._transactional_id = self._generate_transactional_id()
        self.logger = logger.bind(component="approval_kafka_producer")

    def _generate_transactional_id(self) -> str:
        """Generate stable transactional ID per pod."""
        hostname = os.environ.get("HOSTNAME", "local")
        pod_uid = os.environ.get("POD_UID", "0")
        return f"approval-response-producer-{hostname}-{pod_uid}"

    async def initialize(self):
        """Initialize Kafka producer with transaction support."""
        producer_config = {
            "bootstrap.servers": self.settings.bootstrap_servers,
            "enable.idempotence": self.settings.enable_idempotence,
            "transactional.id": self._transactional_id,
            "acks": "all",
            "max.in.flight.requests.per.connection": 5,
        }

        # Add security configuration
        if self.settings.security_protocol != "PLAINTEXT":
            producer_config.update(
                {
                    "security.protocol": self.settings.security_protocol,
                    "sasl.mechanism": self.settings.sasl_mechanism,
                    "sasl.username": self.settings.sasl_username,
                    "sasl.password": self.settings.sasl_password,
                }
            )

        self.producer = Producer(producer_config)

        # Initialize Schema Registry client (optional for dev)
        if self.settings.schema_registry_url and self.settings.schema_registry_url.strip():
            self.logger.info(
                "Initializing Schema Registry for approval response producer",
                url=self.settings.schema_registry_url,
            )

            try:
                self.schema_registry_client = SchemaRegistryClient(
                    {"url": self.settings.schema_registry_url}
                )

                self.avro_serializer = AvroSerializer(
                    self.schema_registry_client, APPROVAL_RESPONSE_SCHEMA
                )
                self.logger.info(
                    "Schema Registry enabled for response producer",
                    url=self.settings.schema_registry_url,
                )
            except Exception as e:
                self.logger.warning(
                    "Failed to initialize Schema Registry - using JSON", error=str(e)
                )
                self.avro_serializer = None
        else:
            self.logger.warning(
                "Schema Registry disabled - using JSON",
                environment=os.environ.get("ENVIRONMENT", "dev"),
            )

        # Initialize transactions
        self.producer.init_transactions()

        self.logger.info(
            "Approval Response Producer initialized",
            transactional_id=self._transactional_id,
            topic=self.settings.approval_responses_topic,
        )

    async def send_approval_response(
        self,
        response: ApprovalResponse,
        headers: Optional[dict[str, Any]] = None,
    ):
        """
        Send approval decision to Kafka.

        R-A3: Publishes to plan_approvals_responses topic.
        INV-4: Maintains Kafka topic contract.

        Args:
            response: ApprovalResponse with the decision
            headers: Optional additional headers (e.g., traceparent)
        """
        if not self.producer:
            raise RuntimeError("Producer not initialized. Call initialize() first.")

        topic = self.settings.approval_responses_topic

        try:
            # Begin transaction
            self.producer.begin_transaction()

            # Serialize response (Avro or JSON)
            if self.avro_serializer:
                kafka_data = response.to_kafka_dict()
                serialization_context = SerializationContext(topic, 0)  # VALUE = 0
                value = self.avro_serializer(kafka_data, serialization_context)
                content_type = "application/avro"
            else:
                value = json.dumps(response.to_kafka_dict(), default=str).encode("utf-8")
                content_type = "application/json"

            # Prepare headers with W3C traceparent propagation support
            message_headers = {
                "plan-id": response.plan_id,
                "intent-id": response.intent_id,
                "decision": response.decision,
                "approved-by": response.approved_by,
                "content-type": content_type,
            }

            # Add custom headers
            if headers:
                message_headers.update(headers)

            # Convert to list of tuples for confluent-kafka
            headers_list = [
                (k, v.encode("utf-8") if isinstance(v, str) else v)
                for k, v in message_headers.items()
            ]

            # Partition key by plan_id
            key = response.plan_id.encode("utf-8")

            # Produce message
            self.producer.produce(
                topic=topic,
                key=key,
                value=value,
                headers=headers_list,
                on_delivery=self._delivery_callback,
            )

            # Flush
            self.producer.flush()

            # Commit transaction
            self.producer.commit_transaction()

            self.logger.info(
                "Approval response published",
                plan_id=response.plan_id,
                intent_id=response.intent_id,
                decision=response.decision,
                approved_by=response.approved_by,
                topic=topic,
                format=content_type,
            )

        except Exception as e:
            self.logger.error(
                "Error publishing approval response",
                plan_id=response.plan_id,
                error=str(e),
            )

            # Abort transaction on error
            self.producer.abort_transaction()
            raise

    def _delivery_callback(self, err, msg):
        """Delivery callback for messages."""
        if err:
            self.logger.error(
                "Approval response delivery failed",
                error=err,
                topic=msg.topic(),
            )
        else:
            self.logger.debug(
                "Approval response delivered",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
            )

    async def close(self):
        """Close producer gracefully."""
        if self.producer:
            self.producer.flush()
            self.logger.info("Approval Response Producer closed")
