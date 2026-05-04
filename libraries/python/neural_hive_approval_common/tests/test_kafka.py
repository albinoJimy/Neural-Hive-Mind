"""
Tests for Approval Kafka Producer.

R-A3: Kafka integration (plan_approvals, plan_approvals_responses topics)
INV-4: Kafka topic contracts
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from neural_hive_approval_common.kafka import (
    ApprovalKafkaProducer,
    ApprovalKafkaProducerSettings,
)
from neural_hive_approval_common.models import ApprovalResponse


class TestApprovalKafkaProducerSettings:
    """Tests for ApprovalKafkaProducerSettings."""

    def test_default_settings(self):
        """Test default settings."""
        settings = ApprovalKafkaProducerSettings(
            bootstrap_servers="localhost:9092"
        )

        assert settings.bootstrap_servers == "localhost:9092"
        assert settings.approval_responses_topic == "plan_approvals_responses"
        assert settings.schema_registry_url is None
        assert settings.security_protocol == "PLAINTEXT"
        assert settings.enable_idempotence is True

    def test_custom_settings(self):
        """Test custom settings."""
        settings = ApprovalKafkaProducerSettings(
            bootstrap_servers="kafka:9092",
            approval_responses_topic="custom-topic",
            schema_registry_url="http://schema-registry:8081",
            security_protocol="SASL_SSL",
            sasl_mechanism="PLAIN",
            sasl_username="user",
            sasl_password="pass",
        )

        assert settings.bootstrap_servers == "kafka:9092"
        assert settings.approval_responses_topic == "custom-topic"
        assert settings.schema_registry_url == "http://schema-registry:8081"
        assert settings.security_protocol == "SASL_SSL"


class TestApprovalKafkaProducer:
    """Tests for ApprovalKafkaProducer.

    R-A3: Kafka integration.
    INV-4: Kafka topic contracts.
    """

    @pytest.fixture()
    def settings(self):
        """Fixture for producer settings."""
        return ApprovalKafkaProducerSettings(
            bootstrap_servers="localhost:9092",
            schema_registry_url=None,  # Disable Schema Registry for tests
        )

    @pytest.fixture()
    def approval_response(self):
        """Fixture for approval response."""
        return ApprovalResponse(
            plan_id="plan-123",
            intent_id="intent-456",
            decision="approved",
            approved_by="user-789",
            approved_at=datetime.now(timezone.utc),
            cognitive_plan={"tasks": []},
        )

    def test_initialization_without_schema_registry(self, settings):
        """Test initialization without Schema Registry."""
        producer = ApprovalKafkaProducer(settings)

        assert producer.settings == settings
        assert producer.schema_registry_client is None
        assert producer.avro_serializer is None

    @pytest.mark.asyncio()
    async def test_initialize_creates_producer(self, settings):
        """Test initialize creates Kafka producer."""
        producer = ApprovalKafkaProducer(settings)

        with patch("neural_hive_approval_common.kafka.Producer") as mock_producer_class:
            mock_producer = MagicMock()
            mock_producer_class.return_value = mock_producer

            await producer.initialize()

            assert producer.producer == mock_producer
            mock_producer.init_transactions.assert_called_once()

    @pytest.mark.asyncio()
    async def test_send_approval_response_json(self, settings, approval_response):
        """Test R-A3: Sending approval response via Kafka (JSON format)."""
        producer = ApprovalKafkaProducer(settings)

        # Mock producer
        mock_producer = MagicMock()
        producer.producer = mock_producer

        # Send response
        await producer.send_approval_response(approval_response)

        # Verify transaction flow
        mock_producer.begin_transaction.assert_called_once()
        mock_producer.produce.assert_called_once()
        mock_producer.flush.assert_called_once()
        mock_producer.commit_transaction.assert_called_once()

        # Verify message content
        call_args = mock_producer.produce.call_args
        topic = call_args[1]["topic"]
        key = call_args[1]["key"]
        headers = call_args[1]["headers"]

        assert topic == "plan_approvals_responses"  # R-A3
        assert key == b"plan-123"  # Partition key by plan_id

        # Verify required headers
        header_dict = {k: v.decode() if isinstance(v, bytes) else v for k, v in headers}
        assert header_dict["plan-id"] == "plan-123"
        assert header_dict["decision"] == "approved"

    @pytest.mark.asyncio()
    async def test_send_approval_response_with_custom_headers(self, settings, approval_response):
        """Test sending response with custom headers (traceparent)."""
        producer = ApprovalKafkaProducer(settings)

        mock_producer = MagicMock()
        producer.producer = mock_producer

        custom_headers = {
            "traceparent": "00-12345678901234567890123456789012-1234567890123456-01",
            "correlation-id": "corr-123",
        }

        await producer.send_approval_response(approval_response, headers=custom_headers)

        call_args = mock_producer.produce.call_args
        headers = call_args[1]["headers"]
        header_dict = {k: v.decode() if isinstance(v, bytes) else v for k, v in headers}

        # Verify custom headers are included
        assert header_dict["traceparent"] == "00-12345678901234567890123456789012-1234567890123456-01"
        assert header_dict["correlation-id"] == "corr-123"

    @pytest.mark.asyncio()
    async def test_send_approval_response_abort_on_error(self, settings, approval_response):
        """Test transaction abort on error."""
        producer = ApprovalKafkaProducer(settings)

        mock_producer = MagicMock()
        mock_producer.produce.side_effect = Exception("Kafka error")
        producer.producer = mock_producer

        with pytest.raises(Exception, match="Kafka error"):
            await producer.send_approval_response(approval_response)

        # Verify abort was called
        mock_producer.abort_transaction.assert_called_once()

    def test_to_kafka_dict_inv4_compatibility(self, approval_response):
        """Test INV-4: Kafka message format compatibility."""
        kafka_dict = approval_response.to_kafka_dict()

        # Verify required INV-4 fields
        assert "plan_id" in kafka_dict
        assert "intent_id" in kafka_dict
        assert "decision" in kafka_dict
        assert "approved_by" in kafka_dict
        assert "approved_at" in kafka_dict
        assert "rejection_reason" in kafka_dict
        assert "cognitive_plan_json" in kafka_dict

        # Verify values
        assert kafka_dict["plan_id"] == "plan-123"
        assert kafka_dict["decision"] == "approved"
        assert kafka_dict["approved_at"] > 0  # Timestamp in ms

    def test_to_kafka_dict_with_rejection(self):
        """Test Kafka dict for rejection."""
        from datetime import datetime
        response = ApprovalResponse(
            plan_id="plan-123",
            intent_id="intent-456",
            decision="rejected",
            approved_by="user-789",
            approved_at=datetime.now(timezone.utc),
            rejection_reason="Security concern",
            cognitive_plan=None,
        )

        kafka_dict = response.to_kafka_dict()

        assert kafka_dict["decision"] == "rejected"
        assert kafka_dict["rejection_reason"] == "Security concern"
        assert kafka_dict["cognitive_plan_json"] is None

    @pytest.mark.asyncio()
    async def test_close_producer(self, settings):
        """Test graceful producer close."""
        producer = ApprovalKafkaProducer(settings)

        mock_producer = MagicMock()
        producer.producer = mock_producer

        await producer.close()

        mock_producer.flush.assert_called_once()
