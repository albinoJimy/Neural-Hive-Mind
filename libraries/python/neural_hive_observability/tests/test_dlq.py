"""
Testes para Dead Letter Queue (DLQ) com Rate Limiter.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from neural_hive_observability.dlq import (
    DLQHandler,
    DLQMessage,
    DLQProducer,
    SlidingWindowRateLimiter,
    TokenBucketRateLimiter,
    create_dlq_handler,
)


class TestDLQMessage:
    """Testes para DLQMessage."""

    def test_create_dlq_message(self):
        """Teste 1: Criar mensagem DLQ com dados mínimos."""
        message = DLQMessage(
            original_topic="test.topic",
            original_partition=0,
            original_offset=123,
            original_key=b"key123",
            original_value=b'{"data": "test"}',
            original_headers=None,
            error_message="Test error",
            error_type="ValueError",
            failure_count=3,
            service="test-service",
            consumer_group="test-group",
        )

        assert message.original_topic == "test.topic"
        assert message.original_partition == 0
        assert message.original_offset == 123
        assert message.failure_count == 3

    def test_dlq_message_to_dict(self):
        """Teste 2: Converter DLQMessage para dict."""
        message = DLQMessage(
            original_topic="test.topic",
            original_partition=0,
            original_offset=123,
            original_key=b"key123",
            original_value=b'{"data": "test"}',
            original_headers=[("x-trace-id", b"abc123")],
            error_message="Test error",
            error_type="ValueError",
            failure_count=3,
        )

        result = message.to_dict()

        assert result["original_topic"] == "test.topic"
        assert result["original_key"] == "6b6579313233"  # hex encoded
        assert result["original_value"] == '{"data": "test"}'
        assert result["original_headers"] == [("x-trace-id", "abc123")]
        assert result["error_type"] == "ValueError"


class TestTokenBucketRateLimiter:
    """Testes para TokenBucketRateLimiter."""

    @pytest.mark.asyncio()
    async def test_initial_tokens(self):
        """Teste 3: Rate limiter inicializado com capacidade máxima."""
        limiter = TokenBucketRateLimiter(capacity=10, refill_rate=1.0)
        assert limiter.get_available_tokens() == 10

    @pytest.mark.asyncio()
    async def test_acquire_single_token(self):
        """Teste 4: Adquirir token único."""
        limiter = TokenBucketRateLimiter(capacity=10, refill_rate=1.0)
        assert await limiter.acquire(1) is True
        assert limiter.get_available_tokens() < 10

    @pytest.mark.asyncio()
    async def test_acquire_multiple_tokens(self):
        """Teste 5: Adquirir múltiplos tokens."""
        limiter = TokenBucketRateLimiter(capacity=10, refill_rate=1.0)
        assert await limiter.acquire(5) is True
        assert await limiter.acquire(6) is False  # Só tem 5 restantes

    @pytest.mark.asyncio()
    async def test_refill_over_time(self):
        """Teste 6: Tokens são repostos ao longo do tempo."""
        limiter = TokenBucketRateLimiter(capacity=10, refill_rate=10.0)

        # Consumir todos os tokens
        await limiter.acquire(10)
        assert limiter.get_available_tokens() < 1

        # Aguardar refill
        await asyncio.sleep(0.15)  # 150ms = ~1.5 tokens a 10/s

        # Deveria ter tokens disponíveis após refill
        assert limiter.get_available_tokens() >= 1

    @pytest.mark.asyncio()
    async def test_acquire_with_timeout_success(self):
        """Teste 7: Adquirir tokens com timeout quando refill permite."""
        limiter = TokenBucketRateLimiter(capacity=5, refill_rate=10.0)

        # Consumir todos os tokens
        await limiter.acquire(5)

        # Tentar adquirir mais com timeout - deve aguardar refill
        assert await limiter.acquire_with_timeout(1, timeout=0.2) is True

    @pytest.mark.asyncio()
    async def test_acquire_with_timeout_failure(self):
        """Teste 8: Timeout quando não há tokens suficientes."""
        limiter = TokenBucketRateLimiter(capacity=5, refill_rate=0.1)  # Baixa taxa

        # Consumir todos os tokens
        await limiter.acquire(5)

        # Tentar adquirir mais com timeout curto - deve falhar
        assert await limiter.acquire_with_timeout(1, timeout=0.05) is False

    @pytest.mark.asyncio()
    async def test_concurrent_acquires(self):
        """Teste 9: Múltiplas aquisições concorrentes são thread-safe."""
        limiter = TokenBucketRateLimiter(capacity=100, refill_rate=50.0)

        async def acquire_many():
            tasks = [limiter.acquire(1) for _ in range(50)]
            results = await asyncio.gather(*tasks)
            return sum(results)

        successful = await acquire_many()
        assert successful == 50


class TestSlidingWindowRateLimiter:
    """Testes para SlidingWindowRateLimiter."""

    @pytest.mark.asyncio()
    async def test_within_limit(self):
        """Teste 10: Requisições dentro do limite são permitidas."""
        limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)

        for _ in range(10):
            assert await limiter.acquire() is True

    @pytest.mark.asyncio()
    async def test_exceeds_limit(self):
        """Teste 11: Requisições além do limite são bloqueadas."""
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)

        for _ in range(5):
            await limiter.acquire()

        # 6ª requisição deve ser bloqueada
        assert await limiter.acquire() is False

    @pytest.mark.asyncio()
    async def test_window_slides(self):
        """Teste 12: Janela desliza permitindo novas requisições."""
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=0.2)

        # Consumir todas as requisições
        for _ in range(3):
            await limiter.acquire()

        assert await limiter.acquire() is False

        # Aguardar janela passar
        await asyncio.sleep(0.25)

        # Agora deve permitir novas requisições
        assert await limiter.acquire() is True


class TestDLQProducer:
    """Testes para DLQProducer."""

    def test_get_dlq_topic(self):
        """Teste 13: Gerar nome do tópico DLQ."""
        producer = DLQProducer(bootstrap_servers="localhost:9092")

        assert producer.get_dlq_topic("test.topic") == "test.topic.dlq"
        assert producer.get_dlq_topic("test.topic.dlq") == "test.topic.dlq"

    @pytest.mark.asyncio()
    async def test_send_dlq_message_success(self):
        """Teste 14: Enviar mensagem para DLQ com sucesso."""
        producer = DLQProducer(bootstrap_servers="localhost:9092")
        producer.producer = AsyncMock()

        dlq_message = DLQMessage(
            original_topic="test.topic",
            original_partition=0,
            original_offset=123,
            original_key=b"key",
            original_value=b'{"test": "data"}',
            original_headers=None,
            error_message="Test error",
            error_type="ValueError",
            failure_count=1,
        )

        result = await producer.send_dlq_message(dlq_message)

        assert result is True
        producer.producer.send_and_wait.assert_called_once()

    @pytest.mark.asyncio()
    async def test_send_dlq_message_without_producer(self):
        """Teste 15: Enviar falha quando producer não iniciado."""
        producer = DLQProducer(bootstrap_servers="localhost:9092")

        dlq_message = DLQMessage(
            original_topic="test.topic",
            original_partition=0,
            original_offset=123,
            original_key=b"key",
            original_value=b'{"test": "data"}',
            original_headers=None,
            error_message="Test error",
            error_type="ValueError",
            failure_count=1,
        )

        result = await producer.send_dlq_message(dlq_message)

        assert result is False

    @pytest.mark.asyncio()
    async def test_send_dlq_message_with_tracing_context(self):
        """Teste 16: Enviar mensagem com contexto de tracing."""
        producer = DLQProducer(bootstrap_servers="localhost:9092")
        producer.producer = AsyncMock()

        dlq_message = DLQMessage(
            original_topic="test.topic",
            original_partition=0,
            original_offset=123,
            original_key=b"key",
            original_value=b'{"test": "data"}',
            original_headers=[("x-trace-id", b"original")],
            error_message="Test error",
            error_type="ValueError",
            failure_count=1,
        )

        tracing_context = {"traceparent": "00-123-456-01", "x-custom-header": "value"}

        result = await producer.send_dlq_message(dlq_message, tracing_context)

        assert result is True

        # Verificar que headers de tracing foram incluídos
        call_args = producer.producer.send_and_wait.call_args
        headers = call_args.kwargs["headers"]
        header_keys = [h[0] for h in headers]
        assert "traceparent" in header_keys


class TestDLQHandler:
    """Testes para DLQHandler."""

    @pytest.fixture()
    def mock_producer(self):
        """Producer mock para testes."""
        producer = Mock(spec=DLQProducer)
        producer.send_dlq_message = AsyncMock(return_value=True)
        producer.get_dlq_topic = Mock(return_value="test.topic.dlq")
        return producer

    @pytest.fixture()
    def mock_message(self):
        """Mensagem Kafka mock."""
        message = Mock()
        message.topic = "test.topic"
        message.partition = 0
        message.offset = 123
        message.key = b"key123"
        message.value = b'{"test": "data"}'
        message.headers = [("x-trace-id", b"trace123")]
        return message

    @pytest.mark.asyncio()
    async def test_below_max_retries_returns_false(self, mock_producer, mock_message):
        """Teste 17: Retorna False quando abaixo do limite de retries."""
        rate_limiter = TokenBucketRateLimiter(capacity=10, refill_rate=10)
        handler = DLQHandler(
            producer=mock_producer,
            rate_limiter=rate_limiter,
            max_retries=5,
        )

        exception = ValueError("Test error")

        # Com 2 falhas (abaixo do limite de 5), deve retornar False (continuar retry)
        result = await handler.handle_failure(
            message=mock_message,
            exception=exception,
            failure_count=2,
        )

        assert result is False
        mock_producer.send_dlq_message.assert_not_called()

    @pytest.mark.asyncio()
    async def test_exceeds_max_retries_sends_to_dlq(self, mock_producer, mock_message):
        """Teste 18: Envia para DLQ quando excede limite de retries."""
        rate_limiter = TokenBucketRateLimiter(capacity=10, refill_rate=10)
        handler = DLQHandler(
            producer=mock_producer,
            rate_limiter=rate_limiter,
            max_retries=3,
        )

        exception = ValueError("Test error")

        # Com 3 falhas (igual ao limite), deve enviar para DLQ
        result = await handler.handle_failure(
            message=mock_message,
            exception=exception,
            failure_count=3,
        )

        assert result is True
        mock_producer.send_dlq_message.assert_called_once()

        # Verificar que a mensagem DLQ foi criada corretamente
        call_args = mock_producer.send_dlq_message.call_args
        dlq_message = call_args[0][0]
        assert dlq_message.failure_count == 3
        assert dlq_message.error_type == "ValueError"

    @pytest.mark.asyncio()
    async def test_rate_limiter_blocks_dlq(self, mock_producer, mock_message):
        """Teste 19: Rate limiter bloqueia envio para DLQ."""
        # Rate limiter vazio (sem tokens)
        rate_limiter = TokenBucketRateLimiter(capacity=0, refill_rate=0)
        handler = DLQHandler(
            producer=mock_producer,
            rate_limiter=rate_limiter,
            max_retries=3,
        )

        exception = ValueError("Test error")

        # Mesmo excedendo retries, não deve enviar se rate limiter bloquear
        result = await handler.handle_failure(
            message=mock_message,
            exception=exception,
            failure_count=5,
        )

        assert result is False
        mock_producer.send_dlq_message.assert_not_called()

    @pytest.mark.asyncio()
    async def test_calculate_backoff(self):
        """Teste 20: Calcular backoff exponencial."""
        handler = DLQHandler(
            producer=Mock(),
            max_retries=3,
            retry_backoff_base=1.0,
        )

        assert handler.calculate_backoff(1) == 2.0  # 2^1
        assert handler.calculate_backoff(2) == 4.0  # 2^2
        assert handler.calculate_backoff(5) == 32.0  # 2^5 (capped)
        assert handler.calculate_backoff(15) == 60.0  # Capped at 60s

    @pytest.mark.asyncio()
    async def test_get_stats(self, mock_producer):
        """Teste 21: Retornar estatísticas do handler."""
        rate_limiter = TokenBucketRateLimiter(capacity=10, refill_rate=10)
        handler = DLQHandler(
            producer=mock_producer,
            rate_limiter=rate_limiter,
        )

        stats = handler.get_stats()

        assert "messages_sent_to_dlq" in stats
        assert "messages_rate_limited" in stats
        assert "available_tokens" in stats
        assert stats["messages_sent_to_dlq"] == 0


class TestCreateDLQHandler:
    """Testes para factory function create_dlq_handler."""

    def test_create_dlq_handler_defaults(self):
        """Teste 22: Criar DLQHandler com configurações padrão."""
        handler = create_dlq_handler(
            bootstrap_servers="localhost:9092",
            service_name="test-service",
            consumer_group="test-group",
        )

        assert isinstance(handler, DLQHandler)
        assert isinstance(handler.producer, DLQProducer)
        assert isinstance(handler.rate_limiter, TokenBucketRateLimiter)
        assert handler.max_retries == 3

    def test_create_dlq_handler_custom_config(self):
        """Teste 23: Criar DLQHandler com configuração customizada."""
        handler = create_dlq_handler(
            bootstrap_servers="localhost:9092",
            service_name="test-service",
            consumer_group="test-group",
            security_protocol="SASL_SSL",
            sasl_mechanism="SCRAM-SHA-256",
            dlq_capacity=200,
            dlq_refill_rate=20.0,
            max_retries=5,
        )

        assert handler.max_retries == 5
        assert handler.rate_limiter.capacity == 200
        assert handler.rate_limiter.refill_rate == 20.0
