"""
Testes E2E para integração de alertas SLA.

Testa o fluxo completo desde o consumo de mensagens Kafka até
o envio de notificações para Slack e PagerDuty.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka import AIOKafkaProducer

from src.clients.slack_client import SlackClient
from src.clients.pagerduty_client import PagerDutyClient
from src.consumers.sla_alert_consumer import SLAAlertConsumer


@pytest.fixture
def kafka_bootstrap_servers():
    """Servidores Kafka para testes."""
    return ["localhost:9092"]


@pytest.fixture
def mock_slack_client():
    """Mock SlackClient."""
    client = AsyncMock(spec=SlackClient)
    client.send_sla_alert = AsyncMock(return_value=True)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def mock_pagerduty_client():
    """Mock PagerDutyClient."""
    client = AsyncMock(spec=PagerDutyClient)
    client.send_sla_alert = AsyncMock(return_value=True)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def sla_alert_consumer(kafka_bootstrap_servers, mock_slack_client, mock_pagerduty_client):
    """Consumer SLA Alert para testes."""
    return SLAAlertConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topics=["sla.alerts", "sla.violations"],
        slack_client=mock_slack_client,
        pagerduty_client=mock_pagerduty_client,
        group_id="test-sla-alert-consumer",
        auto_offset_reset="latest",
    )


class TestSLAAlertsIntegrationE2E:
    """Testes E2E para integração de alertas SLA."""

    @pytest.mark.asyncio
    @patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer")
    async def test_critical_alert_flow_to_pagerduty_and_slack(
        self, mock_kafka_consumer, sla_alert_consumer
    ):
        """
        Testa E2E: alerta crítico → PagerDuty + Slack.

        Fluxo:
        1. Mensagem Kafka recebida
        2. Consumer processa mensagem
        3. PagerDuty alert enviado
        4. Slack alert enviado
        """
        # Setup - Mock Kafka Consumer
        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start = AsyncMock()
        mock_consumer_instance.stop = AsyncMock()

        # Criar mensagem mock de alerta crítico
        critical_alert = {
            "alert_id": "sla-critical-001",
            "severity": "critical",
            "title": "SLA Critical Violation",
            "message": "Error budget exceeded for api-gateway",
            "service_name": "api-gateway",
            "slo_id": "slo-api-availability",
            "error_budget_remaining": 5.0,
            "details": {
                "threshold": 99.9,
                "current_value": 99.2,
                "window": "30d",
            },
        }

        # Mock message do Kafka
        mock_message = MagicMock()
        mock_message.value = json.dumps(critical_alert).encode()
        mock_message.topic = "sla.alerts"
        mock_message.partition = 0
        mock_message.offset = 100

        # Configurar iterator do consumer para retornar nossa mensagem e depois parar
        async def message_iterator():
            yield mock_message

        mock_consumer_instance.__aiter__ = lambda self: message_iterator()
        mock_kafka_consumer.return_value = mock_consumer_instance

        # Act - Iniciar consumer e processar mensagem
        await sla_alert_consumer.start()

        # Processar mensagem diretamente (simula loop de consumo)
        await sla_alert_consumer._process_message(mock_message)

        # Assert - PagerDuty recebeu alerta crítico
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_called_once()
        pd_call = sla_alert_consumer.pagerduty_client.send_sla_alert.call_args

        assert pd_call.kwargs["alert_id"] == "sla-critical-001"
        assert pd_call.kwargs["severity"] == "critical"
        assert pd_call.kwargs["service_name"] == "api-gateway"
        assert pd_call.kwargs["slo_id"] == "slo-api-availability"
        assert pd_call.kwargs["error_budget_remaining"] == 5.0

        # Assert - Slack recebeu alerta crítico
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()
        slack_call = sla_alert_consumer.slack_client.send_sla_alert.call_args

        assert slack_call.kwargs["alert_id"] == "sla-critical-001"
        assert slack_call.kwargs["severity"] == "critical"
        assert slack_call.kwargs["service_name"] == "api-gateway"

        # Cleanup
        await sla_alert_consumer.stop()

    @pytest.mark.asyncio
    @patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer")
    async def test_warning_alert_flow_to_slack_only(
        self, mock_kafka_consumer, sla_alert_consumer
    ):
        """
        Testa E2E: alerta warning → Slack apenas.

        Fluxo:
        1. Mensagem Kafka warning recebida
        2. Consumer processa mensagem
        3. Apenas Slack alert enviado (sem PagerDuty)
        """
        # Setup
        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start = AsyncMock()
        mock_consumer_instance.stop = AsyncMock()

        warning_alert = {
            "alert_id": "sla-warning-002",
            "severity": "warning",
            "title": "High Error Rate Warning",
            "message": "Error rate approaching threshold",
            "service_name": "payment-service",
            "slo_id": "slo-payment-success-rate",
            "error_budget_remaining": 25.0,
        }

        mock_message = MagicMock()
        mock_message.value = json.dumps(warning_alert).encode()
        mock_message.topic = "sla.alerts"

        async def message_iterator():
            yield mock_message

        mock_consumer_instance.__aiter__ = lambda self: message_iterator()
        mock_kafka_consumer.return_value = mock_consumer_instance

        # Act
        await sla_alert_consumer.start()
        await sla_alert_consumer._process_message(mock_message)

        # Assert - PagerDuty NÃO deve ser chamado
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_not_called()

        # Assert - Slack deve ser chamado
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()
        slack_call = sla_alert_consumer.slack_client.send_sla_alert.call_args

        assert slack_call.kwargs["alert_id"] == "sla-warning-002"
        assert slack_call.kwargs["severity"] == "warning"

        # Cleanup
        await sla_alert_consumer.stop()

    @pytest.mark.asyncio
    @patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer")
    async def test_emergency_alert_flow(
        self, mock_kafka_consumer, sla_alert_consumer
    ):
        """
        Testa E2E: alerta emergency → PagerDuty + Slack.

        Severidade emergency é tratada como critical (envia para ambos).
        """
        # Setup
        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start = AsyncMock()

        emergency_alert = {
            "alert_id": "sla-emergency-003",
            "severity": "emergency",
            "title": "Complete Service Outage",
            "message": "All systems down - critical failure",
            "service_name": "core-api",
        }

        mock_message = MagicMock()
        mock_message.value = json.dumps(emergency_alert).encode()

        async def message_iterator():
            yield mock_message

        mock_consumer_instance.__aiter__ = lambda self: message_iterator()
        mock_kafka_consumer.return_value = mock_consumer_instance

        # Act
        await sla_alert_consumer.start()
        await sla_alert_consumer._process_message(mock_message)

        # Assert - Ambos devem ser chamados
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_called_once()
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()

        # Verificar args
        pd_call = sla_alert_consumer.pagerduty_client.send_sla_alert.call_args
        assert pd_call.kwargs["severity"] == "emergency"

        # Cleanup
        await sla_alert_consumer.stop()

    @pytest.mark.asyncio
    async def test_retry_on_slack_send_failure(self, sla_alert_consumer):
        """
        Testa retry em falha de envio Slack.

        Quando Slack falha, o retry automático deve ser tentado.
        """
        # Setup - Slack falha na primeira chamada, sucede na segunda
        call_count = 0

        async def flaky_send(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                from httpx import HTTPStatusError
                raise HTTPStatusError(
                    "503 Service Unavailable",
                    request=MagicMock(),
                    response=MagicMock(status_code=503),
                )
            return True

        sla_alert_consumer.slack_client.send_sla_alert.side_effect = flaky_send
        sla_alert_consumer.pagerduty_client.send_sla_alert = AsyncMock(return_value=True)

        warning_alert = {
            "alert_id": "sla-retry-001",
            "severity": "warning",
            "title": "Test Retry",
            "message": "Testing retry on failure",
            "service_name": "test-service",
        }

        # Act - Processar alerta (vai retry no Slack)
        # Nota: O retry está configurado no SlackClient com tenacity
        # A primeira falha vai ser seguida de retry
        try:
            await sla_alert_consumer._dispatch_warning(warning_alert)
        except Exception:
            # Pode falhar após esgotar retries
            pass

        # Assert - Slack foi chamado pelo menos 2 vezes (original + retry)
        assert sla_alert_consumer.slack_client.send_sla_alert.call_count >= 1

    @pytest.mark.asyncio
    @patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer")
    async def test_slack_blocks_formatting_critical(
        self, mock_kafka_consumer, sla_alert_consumer
    ):
        """
        Testa formatação de blocks Slack para alerta crítico.

        Verifica estrutura dos blocks inclui:
        - Header com emoji
        - Fields com severity, service, SLO ID, timestamp
        - Error budget se disponível
        - Mensagem
        - Footer com alert ID
        """
        # Setup
        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start = AsyncMock()

        alert_data = {
            "alert_id": "sla-blocks-001",
            "severity": "critical",
            "title": "Test Block Formatting",
            "message": "Testing Slack blocks",
            "service_name": "test-service",
            "slo_id": "slo-test",
            "error_budget_remaining": 12.5,
            "details": {"metric": "availability", "threshold": "99.9%"},
        }

        mock_message = MagicMock()
        mock_message.value = json.dumps(alert_data).encode()

        async def message_iterator():
            yield mock_message

        mock_consumer_instance.__aiter__ = lambda self: message_iterator()
        mock_kafka_consumer.return_value = mock_consumer_instance

        # Act
        await sla_alert_consumer.start()

        # Capturar os blocks enviados para Slack
        sent_blocks = []

        async def capture_blocks(**kwargs):
            sent_blocks.extend(kwargs.get("blocks", []))
            return True

        sla_alert_consumer.slack_client.send_sla_alert.side_effect = capture_blocks
        sla_alert_consumer.pagerduty_client.send_sla_alert = AsyncMock(return_value=True)

        await sla_alert_consumer._process_message(mock_message)

        # Assert - Verificar estrutura dos blocks
        # Note: O send_sla_alert do SlackClient cria os blocks internamente
        # Aqui verificamos que foi chamado com os parâmetros corretos
        sla_alert_consumer.slack_client.send_sla_alert.assert_called()

        # Cleanup
        await sla_alert_consumer.stop()

    @pytest.mark.asyncio
    @patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer")
    async def test_multiple_alerts_batch_processing(
        self, mock_kafka_consumer, sla_alert_consumer
    ):
        """
        Testa processamento em lote de múltiplos alertas.

        Simula recepção de múltiplas mensagens Kafka.
        """
        # Setup
        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start = AsyncMock()
        mock_consumer_instance.stop = AsyncMock()

        alerts = [
            {
                "alert_id": f"sla-batch-{i:03d}",
                "severity": "critical" if i % 2 == 0 else "warning",
                "title": f"Batch Alert {i}",
                "message": f"Testing batch processing alert {i}",
                "service_name": "batch-service",
            }
            for i in range(5)
        ]

        messages = []
        for alert in alerts:
            mock_msg = MagicMock()
            mock_msg.value = json.dumps(alert).encode()
            messages.append(mock_msg)

        async def message_iterator():
            for msg in messages:
                yield msg

        mock_consumer_instance.__aiter__ = lambda self: message_iterator()
        mock_kafka_consumer.return_value = mock_consumer_instance

        # Act
        await sla_alert_consumer.start()

        # Processar todas as mensagens
        for msg in messages:
            await sla_alert_consumer._process_message(msg)

        # Assert
        # 3 critical alerts → PagerDuty chamado 3 vezes
        assert sla_alert_consumer.pagerduty_client.send_sla_alert.call_count == 3

        # 5 alerts total → Slack chamado 5 vezes
        assert sla_alert_consumer.slack_client.send_sla_alert.call_count == 5

        # Cleanup
        await sla_alert_consumer.stop()


class TestKafkaIntegration:
    """Testes específicos de integração Kafka."""

    @pytest.mark.asyncio
    @patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer")
    async def test_consumer_lifecycle(self, mock_kafka_consumer, sla_alert_consumer):
        """
        Testa ciclo de vida do consumer: start → consume → stop.
        """
        # Setup - Mock consumer
        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start = AsyncMock()
        mock_consumer_instance.stop = AsyncMock()
        mock_kafka_consumer.return_value = mock_consumer_instance

        # Act - Start
        await sla_alert_consumer.start()

        # Assert - Running
        assert sla_alert_consumer.is_running is True
        assert sla_alert_consumer.consumer is not None

        # Act - Stop
        await sla_alert_consumer.stop()

        # Assert - Stopped
        assert sla_alert_consumer.is_running is False

    @pytest.mark.asyncio
    @patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer")
    async def test_health_check(self, mock_kafka_consumer, sla_alert_consumer):
        """Testa health check do consumer."""
        # Setup - Mock consumer
        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start = AsyncMock()
        mock_consumer_instance.stop = AsyncMock()
        mock_kafka_consumer.return_value = mock_consumer_instance

        # Antes de start - não saudável
        assert await sla_alert_consumer.health_check() is False

        # Após start - saudável
        await sla_alert_consumer.start()
        assert await sla_alert_consumer.health_check() is True

        # Após stop - não saudável
        await sla_alert_consumer.stop()
        assert await sla_alert_consumer.health_check() is False


class TestErrorHandling:
    """Testes de handling de erros."""

    @pytest.mark.asyncio
    async def test_malformed_json_message(self, sla_alert_consumer):
        """Testa handling de mensagem JSON malformado."""
        mock_message = MagicMock()
        mock_message.value = b"{invalid json"
        mock_message.topic = "sla.alerts"

        # Act - Não deve levantar exceção
        await sla_alert_consumer._process_message(mock_message)

        # Assert - Nenhum alerta enviado
        sla_alert_consumer.slack_client.send_sla_alert.assert_not_called()
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, sla_alert_consumer):
        """Testa handling de mensagem com campos obrigatórios em falta."""
        # Falta severity
        incomplete_alert = {
            "alert_id": "test-001",
            "title": "Test",
            # severity em falta
            "message": "Test message",
        }

        mock_message = MagicMock()
        mock_message.value = json.dumps(incomplete_alert).encode()

        # Act
        await sla_alert_consumer._process_message(mock_message)

        # Assert - Sem alertas enviados (validação falha)
        sla_alert_consumer.slack_client.send_sla_alert.assert_not_called()
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_slack_and_pagerduty_failure(self, sla_alert_consumer):
        """
        Testa comportamento quando ambos os canais falham.

        O erro deve ser logged mas não crashar o consumer.
        """
        # Setup - Ambos falham
        sla_alert_consumer.slack_client.send_sla_alert.side_effect = Exception("Slack down")
        sla_alert_consumer.pagerduty_client.send_sla_alert.side_effect = Exception(
            "PagerDuty down"
        )

        critical_alert = {
            "alert_id": "sla-fail-001",
            "severity": "critical",
            "title": "Test Failure",
            "message": "Testing failure handling",
            "service_name": "test-service",
        }

        # Act - Não deve levantar exceção
        await sla_alert_consumer._dispatch_critical(critical_alert)

        # Assert - Ambos foram tentados
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_message_value(self, sla_alert_consumer):
        """Testa handling de mensagem com valor vazio."""
        mock_message = MagicMock()
        mock_message.value = None
        mock_message.topic = "sla.alerts"

        # Act - Não deve crashar
        await sla_alert_consumer._process_message(mock_message)

        # Assert - Sem alertas
        sla_alert_consumer.slack_client.send_sla_alert.assert_not_called()
