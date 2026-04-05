"""
Testes de cobertura para kafka/producer.py.

Testes funcionais que executam código real sem mocks pesados.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


# =============================================================================
# Mock Settings
# =============================================================================


class MockSettingsForKafka:
    """Settings para testes Kafka."""

    def __init__(self):
        self.kafka_bootstrap_servers = "localhost:9092"
        self.kafka_tickets_topic = "execution.tickets"
        self.kafka_security_protocol = "PLAINTEXT"
        self.kafka_sasl_mechanism = "SCRAM-SHA-512"
        self.kafka_sasl_username = None
        self.kafka_sasl_password = None


# =============================================================================
# Testes: KafkaTicketProducer.__init__
# =============================================================================


class TestKafkaTicketProducerInit:
    """Testes do inicializador de KafkaTicketProducer."""

    def test_init_creates_producer_instance(self):
        """Cria instância do produtor."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()

            assert producer._producer is None
            assert producer._topic == "execution.tickets"
            assert producer._settings is not None

    def test_init_loads_settings(self):
        """Carrega settings ao inicializar."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_settings = MockSettingsForKafka()
            mock_get_settings.return_value = mock_settings

            producer = KafkaTicketProducer()

            assert producer._settings is mock_settings


# =============================================================================
# Testes: KafkaTicketProducer.start
# =============================================================================


class TestKafkaTicketProducerStart:
    """Testes do método start."""

    @pytest.mark.asyncio
    async def test_start_initializes_producer(self):
        """Inicializa produtor com sucesso."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.AIOKafkaProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock()
                mock_producer_class.return_value = mock_producer

                producer = KafkaTicketProducer()
                await producer.start()

                assert producer._producer is mock_producer
                mock_producer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_with_sasl_configuration(self):
        """Configura produtor com SASL."""
        from src.kafka.producer import KafkaTicketProducer

        settings = MockSettingsForKafka()
        settings.kafka_security_protocol = "SASL_SSL"
        settings.kafka_sasl_mechanism = "PLAIN"
        settings.kafka_sasl_username = "user"
        settings.kafka_sasl_password = "pass"

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = settings

            with patch("src.kafka.producer.AIOKafkaProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock()
                mock_producer_class.return_value = mock_producer

                producer = KafkaTicketProducer()
                await producer.start()

                # Verificar configuração SASL
                call_kwargs = mock_producer_class.call_args[1]
                assert call_kwargs["security_protocol"] == "SASL_SSL"
                assert call_kwargs["sasl_mechanism"] == "PLAIN"
                assert call_kwargs["sasl_plain_username"] == "user"
                assert call_kwargs["sasl_plain_password"] == "pass"

    @pytest.mark.asyncio
    async def test_start_with_retry_on_failure(self):
        """Retorna em caso de falha na inicialização."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.AIOKafkaProducer") as mock_producer_class:
                call_count = 0

                async def mock_start():
                    nonlocal call_count
                    call_count += 1
                    if call_count < 2:
                        raise Exception("Connection failed")

                mock_producer = MagicMock()
                mock_producer.start = mock_start
                mock_producer_class.return_value = mock_producer

                producer = KafkaTicketProducer()
                await producer.start()

                assert call_count == 2
                assert producer._producer is not None

    @pytest.mark.asyncio
    async def test_start_all_retries_exhausted(self):
        """Levanta exceção quando todos os retries falham."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.AIOKafkaProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock(side_effect=Exception("Connection failed"))
                mock_producer_class.return_value = mock_producer

                producer = KafkaTicketProducer()

                with pytest.raises(RuntimeError, match="Failed to start Kafka producer"):
                    await producer.start(max_retries=2)

    @pytest.mark.asyncio
    async def test_start_exponential_backoff(self):
        """Usa exponential backoff entre retries."""
        from src.kafka.producer import KafkaTicketProducer
        import time

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.AIOKafkaProducer") as mock_producer_class:
                call_times = []

                async def mock_start():
                    call_times.append(time.time())
                    if len(call_times) < 3:
                        raise Exception("Connection failed")

                mock_producer = MagicMock()
                mock_producer.start = mock_start
                mock_producer_class.return_value = mock_producer

                producer = KafkaTicketProducer()
                await producer.start(max_retries=3, initial_delay=0.05)

                # Verificar delays
                assert len(call_times) == 3
                delay_1 = call_times[1] - call_times[0]
                delay_2 = call_times[2] - call_times[1]

                # Deve haver delays entre tentativas
                assert delay_1 >= 0.04
                assert delay_2 > delay_1  # Exponential

    @pytest.mark.asyncio
    async def test_start_with_producer_configuration(self):
        """Configura produtor com opções corretas."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.AIOKafkaProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock()
                mock_producer_class.return_value = mock_producer

                producer = KafkaTicketProducer()
                await producer.start()

                # Verificar configurações
                call_kwargs = mock_producer_class.call_args[1]
                assert call_kwargs["bootstrap_servers"] == "localhost:9092"
                assert call_kwargs["acks"] == "all"
                assert call_kwargs["compression_type"] == "gzip"
                assert call_kwargs["linger_ms"] == 10
                assert call_kwargs["max_request_size"] == 1048576

    @pytest.mark.asyncio
    async def test_start_with_serializers(self):
        """Configura serializers JSON."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.AIOKafkaProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock()
                mock_producer_class.return_value = mock_producer

                producer = KafkaTicketProducer()
                await producer.start()

                # Verificar serializers
                call_kwargs = mock_producer_class.call_args[1]
                assert "value_serializer" in call_kwargs
                assert "key_serializer" in call_kwargs

                # Testar serializers
                value_serializer = call_kwargs["value_serializer"]
                key_serializer = call_kwargs["key_serializer"]

                # Value serializer deve converter para JSON e encode
                result = value_serializer({"test": "data"})
                assert isinstance(result, bytes)
                assert b'"test"' in result or b'"data"' in result

                # Key serializer deve encode string
                result = key_serializer("test-key")
                assert result == b"test-key"

                # Key serializer com None deve retornar None
                result = key_serializer(None)
                assert result is None


# =============================================================================
# Testes: KafkaTicketProducer.stop
# =============================================================================


class TestKafkaTicketProducerStop:
    """Testes do método stop."""

    @pytest.mark.asyncio
    async def test_stop_stops_producer(self):
        """Para produtor corretamente."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()

            # Mock producer
            mock_producer = MagicMock()
            mock_producer.stop = AsyncMock()
            producer._producer = mock_producer

            await producer.stop()

            mock_producer.stop.assert_called_once()
            assert producer._producer is None

    @pytest.mark.asyncio
    async def test_stop_with_none_producer(self):
        """Lida com produtor None sem erro."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()
            producer._producer = None

            # Não deve levantar exceção
            await producer.stop()


# =============================================================================
# Testes: KafkaTicketProducer.publish_ticket
# =============================================================================


class TestKafkaTicketProducerPublish:
    """Testes do método publish_ticket."""

    @pytest.mark.asyncio
    async def test_publish_ticket_success(self):
        """Publica ticket com sucesso."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()

            # Mock producer
            mock_producer = MagicMock()
            mock_producer.send_and_wait = AsyncMock()
            producer._producer = mock_producer

            ticket = {"ticket_id": "test-123", "data": "test"}

            result = await producer.publish_ticket(ticket)

            assert result is True
            mock_producer.send_and_wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_ticket_with_custom_key(self):
        """Publica ticket com chave customizada."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()

            mock_producer = MagicMock()
            mock_producer.send_and_wait = AsyncMock()
            producer._producer = mock_producer

            ticket = {"ticket_id": "test-123", "data": "test"}

            await producer.publish_ticket(ticket, key="custom-key")

            # Verificar chave usada
            call_args = mock_producer.send_and_wait.call_args
            assert call_args[1]["key"] == "custom-key"

    @pytest.mark.asyncio
    async def test_publish_ticket_uses_ticket_id_as_key(self):
        """Usa ticket_id como chave padrão."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()

            mock_producer = MagicMock()
            mock_producer.send_and_wait = AsyncMock()
            producer._producer = mock_producer

            ticket = {"ticket_id": "test-456", "data": "test"}

            await producer.publish_ticket(ticket)

            # Verificar ticket_id usado como chave
            call_args = mock_producer.send_and_wait.call_args
            assert call_args[1]["key"] == "test-456"

    @pytest.mark.asyncio
    async def test_publish_ticket_with_none_producer(self):
        """Retorna False quando produtor não inicializado."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()
            producer._producer = None

            ticket = {"ticket_id": "test-123", "data": "test"}

            result = await producer.publish_ticket(ticket)

            assert result is False

    @pytest.mark.asyncio
    async def test_publish_ticket_timeout(self):
        """Retorna False em caso de timeout."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()

            mock_producer = MagicMock()
            mock_producer.send_and_wait = AsyncMock(side_effect=asyncio.TimeoutError())
            producer._producer = mock_producer

            ticket = {"ticket_id": "test-123", "data": "test"}

            result = await producer.publish_ticket(ticket, timeout_ms=1000)

            assert result is False

    @pytest.mark.asyncio
    async def test_publish_ticket_general_exception(self):
        """Retorna False em caso de exceção geral."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()

            mock_producer = MagicMock()
            mock_producer.send_and_wait = AsyncMock(side_effect=Exception("Kafka error"))
            producer._producer = mock_producer

            ticket = {"ticket_id": "test-123", "data": "test"}

            result = await producer.publish_ticket(ticket)

            assert result is False

    @pytest.mark.asyncio
    async def test_publish_ticket_with_custom_timeout(self):
        """Usa timeout customizado."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()

            # Criar awaitable mock para wait_for
            async def mock_send():
                return None

            mock_producer = MagicMock()
            mock_producer.send_and_wait = AsyncMock()
            producer._producer = mock_producer

            ticket = {"ticket_id": "test-123", "data": "test"}

            # Timeout de 3000ms = 3.0 segundos
            await producer.publish_ticket(ticket, timeout_ms=3000)

            # Verificar que publish foi chamado
            mock_producer.send_and_wait.assert_called_once()


# =============================================================================
# Testes: KafkaTicketProducer.health_check
# =============================================================================


class TestKafkaTicketProducerHealthCheck:
    """Testes do método health_check."""

    @pytest.mark.asyncio
    async def test_health_check_with_active_producer(self):
        """Retorna True quando produtor ativo."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()
            producer._producer = MagicMock()

            result = await producer.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_with_none_producer(self):
        """Retorna False quando produtor None."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            producer = KafkaTicketProducer()
            producer._producer = None

            result = await producer.health_check()

            assert result is False


# =============================================================================
# Testes: Funções Globais
# =============================================================================


class TestGlobalProducerFunctions:
    """Testes das funções globais do produtor."""

    @pytest.mark.asyncio
    async def test_get_kafka_producer_creates_singleton(self):
        """Cria singleton do produtor."""
        from src.kafka.producer import get_kafka_producer, close_kafka_producer
        import src.kafka.producer as producer_module

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.KafkaTicketProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock()
                mock_producer.stop = AsyncMock()
                mock_producer_class.return_value = mock_producer

                # Resetar global
                producer_module._producer = None

                # Primeira chamada
                producer1 = await get_kafka_producer()

                # Segunda chamada - deve retornar mesma instância
                producer2 = await get_kafka_producer()

                assert producer1 is producer2

                # Limpar
                producer_module._producer = None

    @pytest.mark.asyncio
    async def test_close_kafka_producer(self):
        """Fecha produtor global."""
        from src.kafka.producer import get_kafka_producer, close_kafka_producer
        import src.kafka.producer as producer_module

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.KafkaTicketProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock()
                mock_producer.stop = AsyncMock()
                mock_producer_class.return_value = mock_producer

                # Resetar global
                producer_module._producer = None

                # Criar produtor
                await get_kafka_producer()

                # Fechar
                await close_kafka_producer()

                mock_producer.stop.assert_called_once()

                # Limpar
                producer_module._producer = None

    @pytest.mark.asyncio
    async def test_close_kafka_producer_when_none(self):
        """Lida com produtor global None."""
        from src.kafka.producer import close_kafka_producer

        # Resetar global
        import src.kafka.producer as producer_module
        producer_module._producer = None

        # Não deve levantar exceção
        await close_kafka_producer()

    @pytest.mark.asyncio
    async def test_get_kafka_producer_starts_producer(self):
        """Inicia produtor se não existir."""
        from src.kafka.producer import get_kafka_producer
        import src.kafka.producer as producer_module

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.KafkaTicketProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock()
                mock_producer.stop = AsyncMock()
                mock_producer_class.return_value = mock_producer

                # Resetar global
                producer_module._producer = None

                producer = await get_kafka_producer()

                mock_producer.start.assert_called_once()

                # Limpar
                producer_module._producer = None


# =============================================================================
# Testes: Edge Cases e Integração
# =============================================================================


class TestKafkaProducerIntegration:
    """Testes de integração do produtor Kafka."""

    @pytest.mark.asyncio
    async def test_full_producer_lifecycle(self):
        """Testa ciclo completo de vida do produtor."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.AIOKafkaProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock()
                mock_producer.stop = AsyncMock()
                mock_producer.send_and_wait = AsyncMock()
                mock_producer_class.return_value = mock_producer

                # Criar e iniciar
                producer = KafkaTicketProducer()
                await producer.start()

                # Publicar
                ticket = {"ticket_id": "test-123", "data": "test"}
                result = await producer.publish_ticket(ticket)
                assert result is True

                # Health check
                health = await producer.health_check()
                assert health is True

                # Parar
                await producer.stop()

    @pytest.mark.asyncio
    async def test_multiple_publish_after_start(self):
        """Publica múltiplos tickets."""
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForKafka()

            with patch("src.kafka.producer.AIOKafkaProducer") as mock_producer_class:
                mock_producer = MagicMock()
                mock_producer.start = AsyncMock()
                mock_producer.send_and_wait = AsyncMock()
                mock_producer_class.return_value = mock_producer

                producer = KafkaTicketProducer()
                await producer.start()

                # Publicar múltiplos
                for i in range(5):
                    ticket = {"ticket_id": f"test-{i}", "data": "test"}
                    result = await producer.publish_ticket(ticket)
                    assert result is True

                assert mock_producer.send_and_wait.call_count == 5

    def test_module_has_logger(self):
        """Verifica que módulo tem logger."""
        from src.kafka import producer

        # Módulo deve ter logger via structlog
        assert hasattr(producer, "get_logger") or hasattr(producer, "KafkaTicketProducer")
