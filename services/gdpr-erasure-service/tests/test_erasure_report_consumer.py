"""
Testes para ErasureReportConsumer
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.consumers.erasure_report_consumer import ErasureReportConsumer


@pytest.fixture
def mock_settings():
    """Settings mock"""
    settings = MagicMock()
    settings.kafka_erasure_reports_topic = "gdpr.erasure.reports"
    settings.kafka_bootstrap_servers = "localhost:9092"
    return settings


@pytest.fixture
def consumer(mock_settings):
    """Consumer fixture"""
    return ErasureReportConsumer(mock_settings)


class TestErasureReportConsumerInit:
    """Testes para inicializacao"""

    def test_init(self, consumer):
        """Testa inicializacao do consumidor"""
        assert consumer.settings is not None
        assert consumer.consumer is None
        assert consumer.running is False


class TestErasureReportConsumerInitialize:
    """Testes para initialize"""

    @pytest.mark.asyncio
    async def test_initialize(self, consumer):
        """Testa inicializacao do Kafka consumer"""
        with patch("src.consumers.erasure_report_consumer.AIOKafkaConsumer") as mock_kafka:
            mock_consumer = AsyncMock()
            mock_kafka.return_value = mock_consumer

            await consumer.initialize()

            assert consumer.consumer == mock_consumer
            mock_consumer.start.assert_called_once()


class TestErasureReportConsumerProcessMessage:
    """Testes para _process_message"""

    @pytest.mark.asyncio
    async def test_process_message_success(self, consumer):
        """Testa processamento de mensagem com sucesso"""
        # Setup service mock
        service = AsyncMock()
        consumer.set_erasure_service(service)

        report_data = {
            "request_id": "req-123",
            "service": "approval-service",
            "status": "success",
            "records_affected": 42,
        }

        await consumer._process_message(report_data)

        service.handle_erasure_report.assert_called_once_with(report_data)

    @pytest.mark.asyncio
    async def test_process_message_error(self, consumer):
        """Testa processamento com erro"""
        service = AsyncMock()
        service.handle_erasure_report.side_effect = Exception("DB Error")
        consumer.set_erasure_service(service)

        report_data = {"request_id": "req-123"}

        # Nao deve levantar excecao
        await consumer._process_message(report_data)

        service.handle_erasure_report.assert_called_once()


class TestErasureReportConsumerStartConsuming:
    """Testes para start_consuming"""

    @pytest.mark.asyncio
    async def test_start_without_service(self, consumer):
        """Testa erro ao iniciar sem service configurado"""
        consumer.consumer = AsyncMock()  # Primeiro precisa inicializar
        with pytest.raises(RuntimeError, match="ErasureService nao configurado"):
            await consumer.start_consuming()

    @pytest.mark.asyncio
    async def test_start_without_initialize(self, consumer):
        """Testa erro ao iniciar sem inicializar"""
        service = AsyncMock()
        consumer.set_erasure_service(service)

        with pytest.raises(RuntimeError, match="Consumer nao inicializado"):
            await consumer.start_consuming()


class TestErasureReportConsumerClose:
    """Testes para close"""

    @pytest.mark.asyncio
    async def test_close(self, consumer):
        """Testa fechamento do consumidor"""
        mock_consumer = AsyncMock()
        consumer.consumer = mock_consumer
        consumer.running = True

        await consumer.close()

        assert consumer.running is False
        mock_consumer.stop.assert_called_once()
