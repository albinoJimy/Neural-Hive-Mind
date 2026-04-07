"""
Testes para AutocuraEventProducer.
"""
import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_producer():
    """Producer Kafka mockado."""
    with patch("src.clients.autocura_producer.Producer") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


class TestAutocuraEventProducer:
    """Testes para AutocuraEventProducer."""

    def test_init(self, mock_producer):
        """Testa inicialização do producer."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer(
            bootstrap_servers="localhost:9092",
            topic="autocura.events"
        )

        assert producer.bootstrap_servers == "localhost:9092"
        assert producer.topic == "autocura.events"
        assert producer._producer is not None

    def test_publish_agent_degraded(self, mock_producer):
        """Testa publicação de evento de agente degradado."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer("localhost:9092")

        # Mock flush para retornar imediatamente
        mock_producer.return_value.flush.return_value = 0

        result = producer.publish_agent_degraded(
            agent_id="agent-123",
            agent_type="queen-agent",
            status="DEGRADED",
            last_seen=1234567890,
        )

        assert result is True

    def test_publish_agent_unhealthy(self, mock_producer):
        """Testa publicação de evento de agente não saudável."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer("localhost:9092")
        mock_producer.return_value.flush.return_value = 0

        result = producer.publish_agent_unhealthy(
            agent_id="agent-456",
            agent_type="worker-agent",
            status="UNHEALTHY",
            last_seen=1234567890,
        )

        assert result is True

    def test_publish_agent_recovered(self, mock_producer):
        """Testa publicação de evento de recuperação."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer("localhost:9092")
        mock_producer.return_value.flush.return_value = 0

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

    def test_close(self, mock_producer):
        """Testa fechamento do producer."""
        from src.clients.autocura_producer import AutocuraEventProducer

        producer = AutocuraEventProducer("localhost:9092")

        producer.close()

        mock_producer.return_value.flush.assert_called_once_with(timeout=10)
        mock_producer.return_value.close.assert_called_once()

    def test_context_manager(self, mock_producer):
        """Testa uso como context manager."""
        from src.clients.autocura_producer import AutocuraEventProducer

        with AutocuraEventProducer("localhost:9092") as producer:
            assert producer is not None

        mock_producer.return_value.flush.assert_called_once_with(timeout=10)
        mock_producer.return_value.close.assert_called_once()


class TestHealthCheckManagerIntegration:
    """Testes de integração com HealthCheckManager."""

    @pytest.mark.asyncio
    async def test_notify_autocura_with_producer():
        """Testa notificação de autocura com produtor."""
        from src.clients.autocura_producer import AutocuraEventProducer
        from src.models import Agent
        from src.services.health_check_manager import HealthCheckManager

        # Mock do RedisRegistryClient e produtor
        with patch("src.services.health_check_manager.RedisRegistryClient"):
            producer = MagicMock(spec=AutocuraEventProducer)
            producer.publish_agent_degraded.return_value = True

            manager = HealthCheckManager(
                etcd_client=MagicMock(),
                check_interval_seconds=60,
                heartbeat_timeout_seconds=120,
                autocura_producer=producer,
            )

            # Criar agente mock
            agent = MagicMock()
            agent.agent_id = "test-123"
            agent.agent_type.value = "queen-agent"
            agent.status.value = "DEGRADED"
            agent.last_seen.timestamp.return_value = 1234567890

            await manager._notify_autocura(agent)

            producer.publish_agent_degraded.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_autocura_without_producer():
        """Testa notificação de autocura sem produtor (fallback)."""
        from src.services.health_check_manager import HealthCheckManager

        with patch("src.services.health_check_manager.RedisRegistryClient"):
            manager = HealthCheckManager(
                etcd_client=MagicMock(),
                check_interval_seconds=60,
                heartbeat_timeout_seconds=120,
                autocura_producer=None,  # Sem produtor
            )

            # Criar agente mock
            agent = MagicMock()
            agent.agent_id = "test-456"
            agent.agent_type.value = "worker-agent"
            agent.status.value = "UNHEALTHY"
            agent.last_seen.timestamp.return_value = 1234567890

            # Não deve lançar exceção
            await manager._notify_autocura(agent)
