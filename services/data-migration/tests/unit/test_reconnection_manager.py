"""
Testes para ReconnectionManager.

Autor: Neural Hive Mind
Criado: 2026-04-19 (BUG-H-001)
"""

import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator, Callable, Optional, TypeVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.reconnection_manager import (
    ReconnectionConfig,
    ReconnectionManager,
    ReconnectionStats,
    consume_with_reconnection,
    get_reconnection_manager,
)

T = TypeVar("T")


class AsyncIteratorWrapper:
    """Helper para criar async iterators a partir de generators.

    Este wrapper suporta reinicialização após falha, criando um novo
    iterator quando necessário.
    """

    def __init__(self, generator: Callable[[], AsyncIterator[T]]):
        self._generator = generator
        self._iterator: Optional[AsyncIterator[T]] = None

    def __aiter__(self) -> AsyncIterator[T]:
        # Criar novo iterator a cada iteração do for loop
        self._iterator = self._generator()
        return self

    async def __anext__(self) -> T:
        if self._iterator is None:
            self._iterator = self._generator()
        try:
            return await self._iterator.__anext__()
        except StopAsyncIteration:
            raise
        except (ConnectionError, OSError):
            # Após falha, marcar para recriação na próxima iteração
            self._iterator = None
            raise


class TestReconnectionConfig:
    """Testes para configuração de reconexão."""

    def test_default_config(self):
        """Testa configuração padrão."""
        config = ReconnectionConfig()

        assert config.max_retries == 50
        assert config.initial_delay_ms == 1000
        assert config.max_delay_ms == 300000
        assert config.backoff_multiplier == 2.0
        assert config.reset_after_seconds == 60

    def test_calculate_delay_zero_retries(self):
        """Testa delay para primeira tentativa."""
        config = ReconnectionConfig()
        delay = config.calculate_delay(0)

        assert delay == 1.0  # 1000ms / 1000

    def test_calculate_delay_exponential_backoff(self):
        """Testa exponential backoff."""
        config = ReconnectionConfig(
            initial_delay_ms=1000,
            max_delay_ms=60000,
            backoff_multiplier=2.0,
        )

        assert config.calculate_delay(0) == 1.0
        assert config.calculate_delay(1) == 2.0
        assert config.calculate_delay(2) == 4.0
        assert config.calculate_delay(3) == 8.0
        assert config.calculate_delay(4) == 16.0

    def test_calculate_delay_with_max_limit(self):
        """Testa delay respeita limite máximo."""
        config = ReconnectionConfig(
            initial_delay_ms=1000,
            max_delay_ms=5000,
            backoff_multiplier=10.0,
        )

        # Deve bater no limite de 5000ms (5 segundos)
        assert config.calculate_delay(0) == 1.0
        assert config.calculate_delay(1) == 5.0  # Limitado
        assert config.calculate_delay(10) == 5.0  # Limitado


class TestReconnectionStats:
    """Testes para estatísticas de reconexão."""

    def test_default_stats(self):
        """Testa stats inicializam corretamente."""
        stats = ReconnectionStats()

        assert stats.total_reconnections == 0
        assert stats.current_retry_count == 0
        assert stats.last_success_at is None
        assert stats.last_error_at is None
        assert stats.last_error_message is None
        assert stats.is_connected is True

    def test_stats_to_dict(self):
        """Testa conversão para dicionário."""
        stats = ReconnectionStats(
            total_reconnections=5,
            current_retry_count=2,
            last_success_at=datetime.now(timezone.utc),
            is_connected=False,
        )

        d = stats.to_dict()

        assert d["total_reconnections"] == 5
        assert d["current_retry_count"] == 2
        assert d["is_connected"] is False
        assert "last_success_at" in d


class TestReconnectionManager:
    """Testes para ReconnectionManager."""

    def test_init_with_default_config(self):
        """Testa inicialização com config padrão."""
        manager = ReconnectionManager()

        assert manager.stats.is_connected is True
        assert manager.stats.total_reconnections == 0

    def test_init_with_custom_config(self):
        """Testa inicialização com config customizada."""
        config = ReconnectionConfig(max_retries=10)
        manager = ReconnectionManager(config=config)

        assert manager.stats is not None

    @pytest.mark.asyncio()
    async def test_consume_success_resets_retry_count(self):
        """Testa consumo bem-sucedido reseta contador."""

        async def mock_consumer():
            """Mock consumer que yield 3 mensagens."""
            for i in range(3):
                yield MagicMock(key=f"key-{i}", value=f"value-{i}")

        handler = AsyncMock()

        manager = ReconnectionManager()
        messages = []
        async for msg in manager.consume_with_reconnection(
            consumer=mock_consumer(),
            handler=handler,
            topic="test.topic",
        ):
            messages.append(msg)
            if len(messages) >= 3:
                break

        assert len(messages) == 3
        assert handler.call_count == 3
        assert manager.stats.current_retry_count == 0

    @pytest.mark.asyncio()
    async def test_consume_with_handler_error_continues(self):
        """Testa erro no handler não causa reconexão."""

        async def mock_consumer():
            """Mock consumer que yield mensagens."""
            for i in range(3):
                yield MagicMock(key=f"key-{i}", value=f"value-{i}")

        async def failing_handler(msg):
            """Handler que falha na segunda mensagem."""
            if "key-1" in str(msg):
                raise ValueError("Handler error")

        manager = ReconnectionManager()
        messages = []
        async for msg in manager.consume_with_reconnection(
            consumer=mock_consumer(),
            handler=failing_handler,
            topic="test.topic",
        ):
            messages.append(msg)
            if len(messages) >= 3:
                break

        # Deve processar todas as mensagens mesmo com erro
        assert len(messages) == 3
        assert manager.stats.current_retry_count == 0

    @pytest.mark.asyncio()
    async def test_connection_error_triggers_retry(self):
        """Testa erro de conexão incrementa contador."""

        call_count = [0]

        async def failing_generator() -> AsyncIterator:
            """Mock generator que falha após yield."""
            call_count[0] += 1
            if call_count[0] == 1:
                yield MagicMock(key="key", value="value")
            raise ConnectionError("Kafka connection lost")

        async def handler(msg):
            pass

        manager = ReconnectionManager(
            config=ReconnectionConfig(max_retries=2, initial_delay_ms=10)
        )

        consumer = AsyncIteratorWrapper(failing_generator)

        with pytest.raises(ConnectionError):
            async for msg in manager.consume_with_reconnection(
                consumer=consumer,
                handler=handler,
                topic="test.topic",
            ):
                # Primeira mensagem passa, depois erro
                pass

        # Deve ter tentado reconectar
        assert manager.stats.current_retry_count > 0
        assert manager.stats.is_connected is False

    @pytest.mark.asyncio()
    async def test_max_retries_respected(self):
        """Testa limite máximo de tentativas é respeitado."""

        async def always_failing_generator() -> AsyncIterator:
            """Mock generator que sempre falha imediatamente."""
            raise ConnectionError("Always fails")
            yield  # pragma: no cover (nunca alcançado)

        async def handler(msg):
            pass

        manager = ReconnectionManager(
            config=ReconnectionConfig(max_retries=3, initial_delay_ms=10)
        )

        consumer = AsyncIteratorWrapper(always_failing_generator)

        with pytest.raises(ConnectionError) as exc_info:
            async for _ in manager.consume_with_reconnection(
                consumer=consumer,
                handler=handler,
                topic="test.topic",
            ):
                pass

        # A mensagem de erro deve mencionar "tentativas" e max_retries
        assert "tentativas" in str(exc_info.value)
        assert manager.stats.current_retry_count > 3

    @pytest.mark.asyncio()
    async def test_on_reconnect_callback_called(self):
        """Testa callback de reconexão é chamado."""

        async def mock_generator() -> AsyncIterator:
            yield MagicMock(key="key", value="value")

        async def handler(msg):
            pass

        callback = AsyncMock()

        manager = ReconnectionManager()
        manager.stats.current_retry_count = 1  # Simular reconexão anterior

        consumer = AsyncIteratorWrapper(mock_generator)

        async for _ in manager.consume_with_reconnection(
            consumer=consumer,
            handler=handler,
            topic="test.topic",
            on_reconnect=callback,
        ):
            break

        # Callback deve ser chamado após sucesso
        assert callback.call_count == 1
        assert manager.stats.current_retry_count == 0

    @pytest.mark.asyncio()
    async def test_consume_messages_with_retry_recreates_consumer(self):
        """Testa consume_messages_with_retry recria consumer."""

        consumer_count = [0]

        def create_consumer() -> AsyncIterator:
            """Mock factory que cria consumer."""
            consumer_count[0] += 1

            async def mock_generator() -> AsyncIterator:
                if consumer_count[0] < 3:
                    raise ConnectionError("Temporary failure")
                yield MagicMock(key="key", value="value")

            return AsyncIteratorWrapper(mock_generator)

        async def handler(msg):
            pass

        manager = ReconnectionManager(
            config=ReconnectionConfig(max_retries=5, initial_delay_ms=10)
        )

        await manager.consume_messages_with_retry(
            consume_func=create_consumer,
            handler=handler,
            topic="test.topic",
        )

        # Deve ter criado 3 consumidores (2 falharam, 1 funcionou)
        assert consumer_count[0] == 3


class TestGetReconnectionManager:
    """Testes para factory get_reconnection_manager."""

    @patch("src.services.reconnection_manager.get_settings")
    def test_uses_settings_config(self, mock_settings):
        """Testa usa configurações do Settings."""
        from unittest.mock import MagicMock

        mock_settings_instance = MagicMock()
        mock_settings_instance.kafka_reconnect_max_attempts = 100
        mock_settings_instance.kafka_reconnect_initial_delay_ms = 2000
        mock_settings_instance.kafka_reconnect_max_delay_ms = 60000
        mock_settings_instance.kafka_reconnect_backoff_multiplier = 3.0
        mock_settings.return_value = mock_settings_instance

        manager = get_reconnection_manager()

        assert manager._config.max_retries == 100
        assert manager._config.initial_delay_ms == 2000


class TestConsumeWithReconnectionHelper:
    """Testes para função helper consume_with_reconnection."""

    @pytest.mark.asyncio()
    async def test_helper_uses_default_manager(self):
        """Testa helper usa manager padrão do Settings."""

        async def mock_consumer():
            yield MagicMock(key="key", value="value")

        async def handler(msg):
            pass

        # Não deve lançar exceção
        async for _ in consume_with_reconnection(
            consumer=mock_consumer(),
            handler=handler,
            topic="test.topic",
        ):
            break
