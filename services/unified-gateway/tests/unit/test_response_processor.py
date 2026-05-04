"""Testes para o Response Processor."""

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.models.classification import FlowType
from src.models.response import KafkaEvent, ResponseStatus, UnifiedResponse
from src.services.response_processor import ResponseProcessor, get_response_processor


@pytest.fixture
def response_processor():
    """Fixture para Response Processor."""
    processor = ResponseProcessor()
    yield processor
    # Cleanup
    import asyncio

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(processor.close())
    finally:
        loop.close()


@pytest.mark.asyncio
class TestResponseProcessorFormatting:
    """Testes de formatação de resposta."""

    async def test_format_response_success_json(self, response_processor):
        """Testar formatação de resposta JSON bem-sucedida."""
        body = b'{"result": "success", "data": [1, 2, 3]}'
        headers = {"content-type": "application/json"}

        response = await response_processor.format_response(
            request_id="req-123",
            flow_type=FlowType.AF,
            status_code=200,
            body=body,
            headers=headers,
            processing_time_ms=45,
        )

        assert response.status == ResponseStatus.SUCCESS
        assert response.flow_type == "A-F"
        assert response.request_id == "req-123"
        assert response.processing_time_ms == 45
        assert response.data == {"result": "success", "data": [1, 2, 3]}
        assert response.error is None

    async def test_format_response_error(self, response_processor):
        """Testar formatação de resposta com erro."""
        body = b'{"error": "Invalid request"}'
        headers = {}

        response = await response_processor.format_response(
            request_id="req-456",
            flow_type=FlowType.G,
            status_code=400,
            body=body,
            headers=headers,
            processing_time_ms=100,
        )

        assert response.status == ResponseStatus.ERROR
        assert response.flow_type == "G"
        assert response.data == {"error": "Invalid request"}

    async def test_format_response_timeout(self, response_processor):
        """Testar formatação de resposta com timeout."""
        response = await response_processor.format_response(
            request_id="req-789",
            flow_type=FlowType.H,
            status_code=504,
            body=None,
            headers={},
            processing_time_ms=30000,
        )

        assert response.status == ResponseStatus.TIMEOUT
        assert response.flow_type == "H"

    async def test_format_response_non_json_body(self, response_processor):
        """Testar formatação de resposta com corpo não-JSON."""
        body = b"Plain text error message"
        headers = {}

        response = await response_processor.format_response(
            request_id="req-abc",
            flow_type=FlowType.AF,
            status_code=500,
            body=body,
            headers=headers,
            processing_time_ms=50,
        )

        assert response.status == ResponseStatus.ERROR
        assert response.data is None
        assert response.error == "Plain text error message"

    async def test_format_response_with_trace_id(self, response_processor):
        """Testar formatação com trace ID."""
        headers = {"traceparent": "00-1234567890abcdef-1234567890abcdef-01"}

        response = await response_processor.format_response(
            request_id="req-trace",
            flow_type=FlowType.G,
            status_code=200,
            body=b'{"ok": true}',
            headers=headers,
            processing_time_ms=30,
        )

        assert response.trace_id == "00-1234567890abcdef-1234567890abcdef-01"

    async def test_format_response_with_fallback(self, response_processor):
        """Testar formatação com fallback usado."""
        response = await response_processor.format_response(
            request_id="req-fallback",
            flow_type=FlowType.G,  # Alternative flow
            status_code=200,
            body=b'{"result": "from fallback"}',
            headers={},
            processing_time_ms=150,
            gateway_used="requirements-engineering:8010",
            fallback_used=True,
            original_flow_type=FlowType.AF,
        )

        assert response.fallback_used is True
        assert response.original_flow_type == "A-F"
        assert response.gateway_used == "requirements-engineering:8010"


@pytest.mark.asyncio
class TestResponseProcessorKafka:
    """Testes de publicação Kafka."""

    async def test_publish_event_success(self, response_processor):
        """Testar publicação de evento com sucesso."""
        # Mock Kafka producer
        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer.send_and_wait = AsyncMock()

        response_processor._kafka_producer = mock_producer
        response_processor._kafka_connected = True

        success = await response_processor.publish_event(
            request_id="req-kafka",
            flow_type=FlowType.AF,
            status=ResponseStatus.SUCCESS,
            processing_time_ms=50,
            tenant_id="tenant-1",
            user_id="user-1",
        )

        assert success is True
        mock_producer.send_and_wait.assert_called_once()

    async def test_publish_event_kafka_disabled(self, response_processor):
        """Testar publicação quando Kafka está desabilitado."""
        with patch("src.services.response_processor.get_settings") as mock_settings:
            settings = Mock()
            settings.KAFKA_ENABLED = False
            mock_settings.return_value = settings

            success = await response_processor.publish_event(
                request_id="req-no-kafka",
                flow_type=FlowType.G,
                status=ResponseStatus.ERROR,
                processing_time_ms=100,
            )

            assert success is False

    async def test_publish_event_with_error(self, response_processor):
        """Testar publicação de evento de erro."""
        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer.send_and_wait = AsyncMock()

        response_processor._kafka_producer = mock_producer
        response_processor._kafka_connected = True

        success = await response_processor.publish_event(
            request_id="req-err",
            flow_type=FlowType.H,
            status=ResponseStatus.ERROR,
            processing_time_ms=5000,
            error_message="Timeout upstream",
        )

        assert success is True
        call_args = mock_producer.send_and_wait.call_args
        event_value = call_args[1]["value"]
        assert event_value["error_message"] == "Timeout upstream"


@pytest.mark.asyncio
class TestResponseProcessorIntegration:
    """Testes de integração do Response Processor."""

    async def test_process_and_publish_success(self, response_processor):
        """Testar processamento e publicação integrados."""
        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer.send_and_wait = AsyncMock()

        response_processor._kafka_producer = mock_producer
        response_processor._kafka_connected = True

        response, published = await response_processor.process_and_publish(
            request_id="req-int",
            flow_type=FlowType.AF,
            status_code=200,
            body=b'{"result": "ok"}',
            headers={},
            processing_time_ms=40,
            tenant_id="tenant-1",
            user_id="user-1",
        )

        assert response.status == ResponseStatus.SUCCESS
        assert published is True
        mock_producer.send_and_wait.assert_called_once()

    async def test_process_and_publish_kafka_fails(self, response_processor):
        """Testar processamento quando Kafka falha."""
        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(side_effect=Exception("Kafka down"))

        response_processor._kafka_producer = mock_producer
        response_processor._kafka_connected = True

        response, published = await response_processor.process_and_publish(
            request_id="req-kafka-fail",
            flow_type=FlowType.G,
            status_code=200,
            body=b'{"ok": true}',
            headers={},
            processing_time_ms=30,
        )

        # Response deve ser formatada mesmo se Kafka falhar
        assert response.status == ResponseStatus.SUCCESS
        assert published is False


class TestResponseProcessorSingleton:
    """Testes do singleton do Response Processor."""

    def test_get_response_processor_returns_same_instance(self):
        """Testar que singleton retorna mesma instância."""
        processor1 = get_response_processor()
        processor2 = get_response_processor()

        assert processor1 is processor2


class TestUnifiedResponseModel:
    """Testes do modelo UnifiedResponse."""

    def test_unified_response_creation(self):
        """Testar criação de UnifiedResponse."""
        response = UnifiedResponse(
            status=ResponseStatus.SUCCESS,
            flow_type="A-F",
            request_id="req-1",
            processing_time_ms=50,
            data={"result": "ok"},
        )

        assert response.status == ResponseStatus.SUCCESS
        assert response.flow_type == "A-F"
        assert response.request_id == "req-1"
        assert response.data == {"result": "ok"}

    def test_unified_response_with_fallback(self):
        """Testar UnifiedResponse com fallback."""
        response = UnifiedResponse(
            status=ResponseStatus.SUCCESS,
            flow_type="G",
            request_id="req-2",
            processing_time_ms=100,
            fallback_used=True,
            original_flow_type="A-F",
        )

        assert response.fallback_used is True
        assert response.original_flow_type == "A-F"


class TestKafkaEventModel:
    """Testes do modelo KafkaEvent."""

    def test_kafka_event_creation(self):
        """Testar criação de KafkaEvent."""
        event = KafkaEvent(
            event_type="request_completed",
            request_id="req-1",
            flow_type="A-F",
            status=ResponseStatus.SUCCESS,
            processing_time_ms=50,
            timestamp="2026-05-04T12:00:00Z",
        )

        assert event.event_type == "request_completed"
        assert event.request_id == "req-1"
        assert event.status == ResponseStatus.SUCCESS
