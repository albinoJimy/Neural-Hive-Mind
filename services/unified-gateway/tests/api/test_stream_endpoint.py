"""Testes para o endpoint de streaming SSE."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestStreamEndpoint:
    """Testes para GET /api/v1/nhm/stream/{request_id}."""

    def test_stream_health_check(self, client: AsyncClient):
        """Testa health check do endpoint de streaming."""
        response = client.get("/api/v1/nhm/stream")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "unified-gateway-stream"
        assert "status" in data
        assert "redis_available" in data
        assert "stream_timeout_seconds" in data

    def test_stream_invalid_request_id(self, client: AsyncClient):
        """Testa stream com request_id inválido."""
        response = client.get("/api/v1/nhm/stream/ab")

        assert response.status_code == 400

    def test_stream_valid_request_id_format(self, client: AsyncClient):
        """Testa que request_id válido é aceito."""
        response = client.get("/api/v1/nhm/stream/valid-request-id-123")

        # Stream deve ser iniciado (mesmo sem Redis)
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    def test_stream_sse_format(self, client: AsyncClient):
        """Testa formato SSE da resposta."""
        response = client.get("/api/v1/nhm/stream/test-request-123")

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # Verificar cabeçalhos de streaming
        assert "cache-control" in response.headers
        assert (
            "no-cache" in response.headers["cache-control"]
            or "no-cache" in response.headers.get("cache-control", "").lower()
        )

    def test_stream_timeout_parameter(self, client: AsyncClient):
        """Testa parâmetro de timeout."""
        response = client.get("/api/v1/nhm/stream/test-request-123?timeout=10")

        assert response.status_code == 200

    def test_stream_timeout_validation(self, client: AsyncClient):
        """Testa validação do timeout (mínimo 5s)."""
        response = client.get("/api/v1/nhm/stream/test-request-123?timeout=1")

        assert response.status_code == 422  # Validation error

    def test_stream_timeout_max_validation(self, client: AsyncClient):
        """Testa validação do timeout (máximo 300s)."""
        response = client.get("/api/v1/nhm/stream/test-request-123?timeout=500")

        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
class TestStreamEvents:
    """Testes para eventos SSE."""

    async def test_sse_event_format(self):
        """Testa formato de evento SSE."""
        from src.api.routers.stream import _generate_sse, StreamEvent

        event = StreamEvent(
            event="test",
            data={"message": "hello"},
            retry=3000,
        )

        sse_string = await _generate_sse(event)

        assert "event: test\n" in sse_string
        assert 'data: {"message": "hello"}\n' in sse_string
        assert "retry: 3000\n" in sse_string
        assert sse_string.endswith("\n\n")

    async def test_sse_event_without_retry(self):
        """Testa evento SSE sem retry."""
        from src.api.routers.stream import _generate_sse, StreamEvent

        event = StreamEvent(
            event="keep-alive",
            data={"timestamp": "2026-05-07T10:00:00"},
        )

        sse_string = await _generate_sse(event)

        assert "event: keep-alive\n" in sse_string
        assert "data:" in sse_string
        assert "retry:" not in sse_string

    async def test_connected_event(self):
        """Testa evento inicial de conexão."""
        from src.api.routers.stream import _generate_sse, StreamEvent

        event = StreamEvent(
            event="connected",
            data={"request_id": "test-123", "message": "Stream connected"},
            retry=3000,
        )

        sse_string = await _generate_sse(event)

        assert "event: connected\n" in sse_string
        assert '"request_id": "test-123"' in sse_string

    async def test_completed_event(self):
        """Testa evento de completion."""
        from src.api.routers.stream import _generate_sse, StreamEvent

        event = StreamEvent(
            event="completed",
            data={
                "request_id": "test-123",
                "status": "completed",
                "flow_type": "G",
            },
        )

        sse_string = await _generate_sse(event)

        assert "event: completed\n" in sse_string
        assert '"status": "completed"' in sse_string

    async def test_error_event(self):
        """Testa evento de erro."""
        from src.api.routers.stream import _generate_sse, StreamEvent

        event = StreamEvent(
            event="error",
            data={
                "request_id": "test-123",
                "status": "failed",
                "error": "Processing failed",
            },
        )

        sse_string = await _generate_sse(event)

        assert "event: error\n" in sse_string
        assert '"error": "Processing failed"' in sse_string


@pytest.mark.asyncio
class TestStreamIntegration:
    """Testes de integração para streaming."""

    @patch("src.api.routers.stream.get_redis_client")
    async def test_stream_with_completed_request(self, mock_get_redis):
        """Testa stream com request já completado."""
        from src.api.routers.stream import _status_event_generator

        # Mock Redis com request completado
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        completed_data = {
            "request_id": "test-completed-123",
            "status": "completed",
            "flow_type": "G",
            "processing_time_ms": 50,
        }

        async def mock_get_return(*args, **kwargs):
            return json.dumps(completed_data)

        mock_redis.get = mock_get_return

        # Coletar eventos
        events = []
        async for event in _status_event_generator("test-completed-123", timeout_seconds=1):
            events.append(event)

        # Verificar eventos recebidos
        assert len(events) > 0
        assert any("event: connected" in e for e in events)
        assert any("event: completed" in e for e in events)

    @patch("src.api.routers.stream.get_redis_client")
    async def test_stream_without_redis(self, mock_get_redis):
        """Testa stream quando Redis não está disponível."""
        from src.api.routers.stream import _status_event_generator

        mock_get_redis.return_value = None

        # Coletar eventos
        events = []
        async for event in _status_event_generator("test-no-redis", timeout_seconds=2):
            events.append(event)
            if len(events) > 2:  # Limitar coleta
                break

        # Deve ter evento connected e keep-alive
        assert len(events) > 0
        assert any("event: connected" in e for e in events)
