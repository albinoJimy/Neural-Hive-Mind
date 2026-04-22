"""
Testes para o Health Monitor Service.

Este módulo testa a detecção automática de problemas nos serviços:
- check_service_health: Verifica se um serviço está saudável
- check_kafka_consumer_lag: Verifica lag de consumidores Kafka
- check_database_connection: Verifica conectividade com banco de dados
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services.health_monitor import ConnectionStatus, HealthMonitor, HealthStatus, LagStatus


class TestHealthMonitor:
    """Testes para o HealthMonitor."""

    @pytest.fixture()
    def health_monitor(self, mock_service_registry_client):
        """Fixture do HealthMonitor."""
        return HealthMonitor(
            service_registry_client=mock_service_registry_client, check_interval_seconds=30
        )

    @pytest.mark.asyncio()
    async def test_check_service_health_healthy(self, health_monitor, mock_service_registry_client):
        """Testa detecção de serviço saudável."""
        mock_service_registry_client.get_service_address = AsyncMock(
            return_value="http://worker-agents:8000"
        )
        mock_service_registry_client.health_check = AsyncMock(return_value=True)

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response

            status = await health_monitor.check_service_health("worker-agents")

        assert status.healthy is True
        assert status.service_name == "worker-agents"
        assert status.checked_at is not None

    @pytest.mark.asyncio()
    async def test_check_service_health_unhealthy(self, health_monitor):
        """Testa detecção de serviço não saudável."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 503
            mock_get.return_value.__aenter__.return_value = mock_response

            status = await health_monitor.check_service_health("worker-agents")

        assert status.healthy is False
        assert status.error_message is not None

    @pytest.mark.asyncio()
    async def test_check_kafka_consumer_lag_ok(self, health_monitor):
        """Testa verificação de lag dentro do limite."""
        from unittest.mock import patch

        from aiokafka.structs import TopicPartition

        # Mock do AIOKafkaConsumer com métodos sincrónicos para committed/highwater
        with patch("aiokafka.AIOKafkaConsumer") as mock_consumer_class:
            mock_consumer = MagicMock()

            # committed e highwater retornam coroutines
            async def mock_committed(tps):
                return {TopicPartition("test-topic", 0): 1000}

            async def mock_highwater(tps):
                return {TopicPartition("test-topic", 0): 1050}

            async def mock_stop():
                pass

            mock_consumer.committed = mock_committed
            mock_consumer.highwater = mock_highwater
            mock_consumer.stop = mock_stop
            mock_consumer.partitions_for_topic = MagicMock(return_value=[0])
            mock_consumer_class.return_value = mock_consumer

            lag_status = await health_monitor.check_kafka_consumer_lag("test-group", "test-topic")

        assert lag_status.lag == 50
        assert lag_status.within_threshold is True
        assert lag_status.threshold == 10000

    @pytest.mark.asyncio()
    async def test_check_kafka_consumer_lag_high(self, health_monitor):
        """Testa verificação de lag acima do limite."""
        from unittest.mock import patch

        from aiokafka.structs import TopicPartition

        with patch("aiokafka.AIOKafkaConsumer") as mock_consumer_class:
            mock_consumer = MagicMock()

            async def mock_committed(tps):
                return {TopicPartition("test-topic", 0): 1000}

            async def mock_highwater(tps):
                return {TopicPartition("test-topic", 0): 15000}

            async def mock_stop():
                pass

            mock_consumer.committed = mock_committed
            mock_consumer.highwater = mock_highwater
            mock_consumer.stop = mock_stop
            mock_consumer.partitions_for_topic = MagicMock(return_value=[0])
            mock_consumer_class.return_value = mock_consumer

            lag_status = await health_monitor.check_kafka_consumer_lag("test-group", "test-topic")

        assert lag_status.lag == 14000
        assert lag_status.within_threshold is False

    @pytest.mark.asyncio()
    async def test_check_database_connection_ok(self, health_monitor):
        """Testa conexão com banco de dados funcionando."""
        with patch("motor.motor_asyncio.AsyncIOMotorClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.admin.command = AsyncMock(return_value={"ok": 1.0})
            mock_client_class.return_value = mock_client

            status = await health_monitor.check_database_connection("mongodb://localhost:27017")

        assert status.connected is True
        assert status.connection_string == "mongodb://localhost:27017"

    @pytest.mark.asyncio()
    async def test_check_database_connection_failed(self, health_monitor):
        """Testa falha de conexão com banco de dados."""
        with patch("motor.motor_asyncio.AsyncIOMotorClient") as mock_client_class:
            mock_client_class.side_effect = Exception("Connection refused")

            status = await health_monitor.check_database_connection("mongodb://localhost:27017")

        assert status.connected is False
        assert status.error is not None

    def test_health_status_model(self):
        """Testa o modelo HealthStatus."""
        status = HealthStatus(
            service_name="test-service", healthy=True, checked_at=datetime.now(UTC)
        )
        assert status.service_name == "test-service"
        assert status.healthy is True

    def test_lag_status_model(self):
        """Testa o modelo LagStatus."""
        status = LagStatus(
            consumer_group="test-group",
            topic="test-topic",
            lag=100,
            threshold=10000,
            within_threshold=True,
        )
        assert status.lag == 100
        assert status.within_threshold is True

    def test_connection_status_model(self):
        """Testa o modelo ConnectionStatus."""
        status = ConnectionStatus(
            connection_string="mongodb://localhost:27017", connected=True, database_type="mongodb"
        )
        assert status.connected is True
        assert status.database_type == "mongodb"
