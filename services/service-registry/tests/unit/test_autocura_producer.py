"""
Testes para AutocuraEventProducer.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_kafka():
    """Mock do módulo Kafka."""
    with (
        patch("src.clients.autocura_producer.KafkaError") as mock_kafka_error,
        patch("src.clients.autocura_producer.Producer") as mock_producer,
    ):
        # Configurar mock do Producer
        producer_instance = MagicMock()
        producer_instance.flush.return_value = 0  # Sem mensagens pendentes
        mock_producer.return_value = producer_instance
        yield mock_producer, mock_kafka_error


class TestAutocuraEventProducer:
    """Testes para AutocuraEventProducer."""

    def test_init(self, mock_kafka):
        """Testa inicialização do producer."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer(
            bootstrap_servers="localhost:9092", topic="autocura.events"
        )

        assert producer.bootstrap_servers == "localhost:9092"
        assert producer.topic == "autocura.events"
        assert producer._producer is not None

    def test_publish_agent_degraded(self, mock_kafka):
        """Testa publicação de evento de agente degradado."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer("localhost:9092")

        # O mock já está configurado para flush retornar 0
        result = producer.publish_agent_degraded(
            agent_id="agent-123",
            agent_type="queen-agent",
            status="DEGRADED",
            last_seen=1234567890,
        )

        assert result is True

    def test_publish_agent_unhealthy(self, mock_kafka):
        """Testa publicação de evento de agente não saudável."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer("localhost:9092")

        result = producer.publish_agent_unhealthy(
            agent_id="agent-456",
            agent_type="worker-agent",
            status="UNHEALTHY",
            last_seen=1234567890,
        )

        assert result is True

    def test_publish_agent_recovered(self, mock_kafka):
        """Testa publicação de evento de recuperação."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer("localhost:9092")

        result = producer.publish_agent_recovered(
            agent_id="agent-789",
            agent_type="scout-agent",
            status="HEALTHY",
        )

        assert result is True

    def test_publish_without_producer(self):
        """Testa publicação quando producer não está disponível."""
        from src.clients.autocura_producer import AutocuraEventProducer

        # Criar producer sem inicializar (falha na criação)
        producer = AutocuraEventProducer.__new__(AutocuraEventProducer)
        producer._producer = None

        result = producer.publish_agent_degraded(
            agent_id="agent-123",
            agent_type="queen-agent",
            status="DEGRADED",
            last_seen=1234567890,
        )

        assert result is False

    def test_close(self, mock_kafka):
        """Testa fechamento do producer."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer("localhost:9092")
        mock_producer_instance = producer._producer

        producer.close()

        # Verificar que flush foi chamado
        mock_producer_instance.flush.assert_called_once_with(timeout=10)

    def test_context_manager(self, mock_kafka):
        """Testa uso como context manager."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer("localhost:9092")
        mock_producer_instance = producer._producer

        with producer as p:
            assert p is not None

        mock_producer_instance.flush.assert_called_once_with(timeout=10)


class TestHealthCheckManagerIntegration:
    """Testes de integração com HealthCheckManager."""

    @pytest.mark.asyncio
    async def test_notify_autocura_with_producer(self):
        """Testa notificação de autocura com produtor."""
        from src.clients.autocura_producer import AutocuraEventProducer
        from src.services.health_check_manager import HealthCheckManager

        # Mock do Producer
        with patch("src.clients.autocura_producer.Producer") as mock_producer_cls:
            producer_instance = MagicMock()
            producer_instance.flush.return_value = 0
            mock_producer_cls.return_value = producer_instance

            # Mock do RedisRegistryClient
            with patch("src.services.health_check_manager.RedisRegistryClient"):
                # Criar produtor real com Producer mockado
                producer = AutocuraEventProducer("localhost:9092")

                manager = HealthCheckManager(
                    redis_client=MagicMock(),
                    check_interval_seconds=60,
                    heartbeat_timeout_seconds=120,
                    autocura_producer=producer,
                )

                # Criar agente mock
                agent = MagicMock()
                agent.agent_id = "test-123"
                agent.agent_type.value = "queen-agent"
                agent.status.value = "DEGRADED"
                agent.last_seen = 1234567890

                # Não deve lançar exceção
                await manager._notify_autocura(agent)

    @pytest.mark.asyncio
    async def test_notify_autocura_without_producer(self):
        """Testa notificação de autocura sem produtor (fallback)."""
        from src.services.health_check_manager import HealthCheckManager

        with patch("src.services.health_check_manager.RedisRegistryClient"):
            manager = HealthCheckManager(
                redis_client=MagicMock(),
                check_interval_seconds=60,
                heartbeat_timeout_seconds=120,
                autocura_producer=None,  # Sem produtor
            )

            # Criar agente mock
            agent = MagicMock()
            agent.agent_id = "test-456"
            agent.agent_type.value = "worker-agent"
            agent.status.value = "UNHEALTHY"
            agent.last_seen = 1234567890

            # Não deve lançar exceção
            await manager._notify_autocura(agent)
