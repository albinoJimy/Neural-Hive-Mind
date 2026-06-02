"""Testes de integração Kafka para Test Generation.

Autor: Neural Hive Mind
Criado: 2026-04-19 (FEAT-G-001)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.consumers.requirements_consumer import RequirementsConsumer
from src.producers.tests_producer import TestsProducer


@pytest.mark.asyncio()
class TestRequirementsConsumer:
    """Testes para RequirementsConsumer."""

    @pytest.mark.asyncio()
    async def test_consumer_starts_successfully(self):
        """Testa que o consumidor inicia corretamente."""
        mock_generator = AsyncMock()
        consumer = RequirementsConsumer(test_generator=mock_generator)

        # Patch AIOKafkaConsumer to avoid real Kafka connection
        with patch("src.consumers.requirements_consumer.AIOKafkaConsumer") as mock_kafka_consumer:
            mock_consumer_instance = AsyncMock()
            mock_consumer_instance.start = AsyncMock()
            mock_kafka_consumer.return_value = mock_consumer_instance

            await consumer.start()

            mock_consumer_instance.start.assert_called_once()
            assert consumer.is_connected

    @pytest.mark.asyncio()
    async def test_consumer_handles_valid_message(self):
        """Testa processamento de mensagem válida."""
        mock_generator = AsyncMock()
        consumer = RequirementsConsumer(test_generator=mock_generator)

        # Mock message
        mock_msg = MagicMock()
        mock_msg.topic = "requirements.generated"
        mock_msg.partition = 0
        mock_msg.offset = 100
        mock_msg.key = b"test-key"
        mock_msg.value = json.dumps(
            {
                "requirements_set_id": "REQ-SET-123",
                "plan_id": "plan-456",
                "requirements": [
                    {
                        "id": "REQ-001",
                        "title": "User Authentication",
                        "description": "Users can authenticate with email/password",
                    }
                ],
            }
        ).encode("utf-8")

        # Mock test generator
        consumer._test_generator = AsyncMock()
        consumer._test_generator.generate_tests = AsyncMock(
            return_value=MagicMock(total_tests_generated=5, test_suite=MagicMock(id="TS-123"))
        )

        # Process message
        await consumer._process_message(mock_msg)

        # Verify generator was called
        consumer._test_generator.generate_tests.assert_called_once()

    @pytest.mark.asyncio()
    async def test_consumer_handles_empty_requirements(self):
        """Testa que consumidor lida com requisitos vazios."""
        mock_generator = AsyncMock()
        consumer = RequirementsConsumer(test_generator=mock_generator)
        consumer._logger = MagicMock()

        mock_msg = MagicMock()
        mock_msg.topic = "requirements.generated"
        mock_msg.offset = 100
        mock_msg.value = json.dumps(
            {
                "requirements_set_id": "REQ-SET-123",
                "plan_id": "plan-456",
                "requirements": [],
            }
        ).encode("utf-8")

        # Process message
        await consumer._process_message(mock_msg)

        # Verify warning was logged
        consumer._logger.warning.assert_called()

    @pytest.mark.asyncio()
    async def test_consumer_handles_invalid_json(self):
        """Testa que consumidor lida com JSON inválido."""
        mock_generator = AsyncMock()
        consumer = RequirementsConsumer(test_generator=mock_generator)
        consumer._logger = MagicMock()

        mock_msg = MagicMock()
        mock_msg.topic = "requirements.generated"
        mock_msg.offset = 100
        mock_msg.value = b"invalid json"

        # Process message
        await consumer._process_message(mock_msg)

        # Verify error was logged
        consumer._logger.error.assert_called()

    @pytest.mark.asyncio()
    async def test_health_check_returns_connected_status(self):
        """Testa que health check retorna status de conexão."""
        mock_generator = AsyncMock()
        consumer = RequirementsConsumer(test_generator=mock_generator)
        consumer._running = True
        consumer._consumer = MagicMock()

        health = await consumer.health_check()

        assert health["kafka_connected"] is True
        assert health["topic"] == "requirements.generated"


@pytest.mark.asyncio()
class TestKafkaProducer:
    """Testes para TestsProducer."""

    @pytest.mark.asyncio()
    async def test_producer_starts_successfully(self):
        """Testa que o produtor inicia corretamente."""
        producer = TestsProducer()

        # Patch AIOKafkaProducer to avoid real Kafka connection
        with patch("src.producers.tests_producer.AIOKafkaProducer") as mock_kafka_producer:
            mock_producer_instance = AsyncMock()
            mock_producer_instance.start = AsyncMock()
            mock_kafka_producer.return_value = mock_producer_instance

            await producer.start()

            mock_producer_instance.start.assert_called_once()
            assert producer.is_connected

    @pytest.mark.asyncio()
    async def test_publish_tests_generated_succeeds(self):
        """Testa publicação de evento tests.generated."""
        producer = TestsProducer()

        with patch.object(producer, "_producer") as mock_producer_impl:
            mock_producer_impl.send_and_wait = AsyncMock()

            await producer.publish_tests_generated(
                test_suite_id="TS-123",
                requirements_set_id="REQ-SET-456",
                plan_id="plan-789",
                tests_count=10,
                test_types=["unit", "integration"],
            )

            mock_producer_impl.send_and_wait.assert_called_once()

            call_args = mock_producer_impl.send_and_wait.call_args
            assert call_args.kwargs["key"] == "TS-123"

    @pytest.mark.asyncio()
    async def test_publish_with_test_suite_data(self):
        """Testa publicação com dados completos da suíte."""
        producer = TestsProducer()

        mock_test_suite = MagicMock()
        mock_test_suite.name = "Authentication Tests"
        mock_test_suite.description = "Tests for user authentication"
        mock_test_suite.framework.value = "pytest"
        mock_test_suite.language = "python"

        with patch.object(producer, "_producer") as mock_producer_impl:
            mock_producer_impl.send_and_wait = AsyncMock()

            await producer.publish_tests_generated(
                test_suite_id="TS-123",
                requirements_set_id="REQ-SET-456",
                plan_id="plan-789",
                tests_count=10,
                test_types=["unit"],
                test_suite=mock_test_suite,
            )

            call_args = mock_producer_impl.send_and_wait.call_args
            event_data = call_args.kwargs["value"]

            assert event_data["test_suite_name"] == "Authentication Tests"
            assert event_data["framework"] == "pytest"

    @pytest.mark.asyncio()
    async def test_health_check_returns_connected_status(self):
        """Testa que health check retorna status de conexão."""
        producer = TestsProducer()
        producer._running = True
        producer._producer = MagicMock()

        health = await producer.health_check()

        assert health["kafka_connected"] is True
        assert health["topic"] == "tests.generated"


@pytest.mark.asyncio()
class TestKafkaIntegrationFlow:
    """Testes de fluxo completo Kafka."""

    @pytest.mark.asyncio()
    async def test_end_to_end_flow(self):
        """Testa fluxo completo: mensagem → consumo → geração → publicação."""
        # Setup consumer and producer
        mock_generator = AsyncMock()
        mock_generator.generate_tests = AsyncMock(
            return_value=MagicMock(total_tests_generated=2, test_suite=MagicMock(id="TS-FLOW"))
        )
        consumer = RequirementsConsumer(test_generator=mock_generator)
        producer = TestsProducer()

        # Mock Kafka components to avoid real connection
        with (
            patch("src.consumers.requirements_consumer.AIOKafkaConsumer") as mock_kafka_consumer,
            patch("src.producers.tests_producer.AIOKafkaProducer") as mock_kafka_producer,
        ):
            mock_consumer_instance = AsyncMock()
            mock_consumer_instance.start = AsyncMock()
            mock_kafka_consumer.return_value = mock_consumer_instance

            mock_producer_instance = AsyncMock()
            mock_producer_instance.start = AsyncMock()
            mock_producer_instance.send_and_wait = AsyncMock()
            mock_kafka_producer.return_value = mock_producer_instance

            await consumer.start()
            await producer.start()

            # Prepare message
            test_msg = MagicMock()
            test_msg.topic = "requirements.generated"
            test_msg.offset = 1
            test_msg.key = b"test-flow"
            test_msg.value = json.dumps(
                {
                    "requirements_set_id": "REQ-SET-FLOW",
                    "plan_id": "plan-flow",
                    "requirements": [
                        {
                            "id": "REQ-FLOW-001",
                            "title": "Flow Test Requirement",
                            "description": "Requirement for flow testing",
                        }
                    ],
                }
            ).encode("utf-8")

            # Process message
            await consumer._process_message(test_msg)

            # Verify test was generated
            assert consumer._test_generator.generate_tests.called

            # Publish result
            result = consumer._test_generator.generate_tests.return_value
            result.test_suite.id = "TS-FLOW"
            result.total_tests_generated = 2

            await producer.publish_tests_generated(
                test_suite_id=result.test_suite.id,
                requirements_set_id="REQ-SET-FLOW",
                plan_id="plan-flow",
                tests_count=result.total_tests_generated,
                test_types=["unit"],
            )

            # Verify publish was called
            mock_producer_instance.send_and_wait.assert_called_once()

            # Cleanup
            await consumer.stop()
            await producer.stop()

    @pytest.mark.asyncio()
    async def test_consumer_publishes_to_producer_automatically(self):
        """Testa que consumer publica evento automaticamente após gerar testes."""
        # Setup mock generator que retorna resultado completo
        mock_result = MagicMock()
        mock_result.total_tests_generated = 5
        mock_result.test_suite.id = "TS-AUTO-001"
        mock_result.test_suite.name = "Auto Tests"
        mock_result.test_suite.description = "Generated automatically"
        mock_result.test_suite.framework.value = "pytest"
        mock_result.test_suite.language = "python"
        mock_result.test_suite.test_cases = [
            MagicMock(test_type=MagicMock(value="unit")),
            MagicMock(test_type=MagicMock(value="unit")),
            MagicMock(test_type=MagicMock(value="integration")),
        ]

        mock_generator = AsyncMock()
        mock_generator.generate_tests = AsyncMock(return_value=mock_result)

        # Setup producer mock
        mock_producer = AsyncMock()
        mock_producer.publish_tests_generated = AsyncMock()

        # Criar consumer com producer
        consumer = RequirementsConsumer(
            test_generator=mock_generator,
            producer=mock_producer,
        )

        # Preparar mensagem
        test_msg = MagicMock()
        test_msg.topic = "requirements.generated"
        test_msg.offset = 100
        test_msg.key = b"auto-test"
        test_msg.value = json.dumps(
            {
                "requirements_set_id": "REQ-SET-AUTO",
                "plan_id": "plan-auto",
                "requirements": [
                    {
                        "id": "REQ-AUTO-001",
                        "title": "Auto Test",
                        "description": "Test auto publishing",
                    }
                ],
            }
        ).encode("utf-8")

        # Processar mensagem
        await consumer._process_message(test_msg)

        # Verificar que testes foram gerados
        mock_generator.generate_tests.assert_called_once()

        # Verificar que evento foi publicado automaticamente
        mock_producer.publish_tests_generated.assert_called_once()

        # Verificar argumentos da publicação
        call_args = mock_producer.publish_tests_generated.call_args
        assert call_args.kwargs["test_suite_id"] == "TS-AUTO-001"
        assert call_args.kwargs["requirements_set_id"] == "REQ-SET-AUTO"
        assert call_args.kwargs["plan_id"] == "plan-auto"
        assert call_args.kwargs["tests_count"] == 5
        assert "unit" in call_args.kwargs["test_types"]
        assert "integration" in call_args.kwargs["test_types"]
        assert call_args.kwargs["test_suite"] == mock_result.test_suite

    @pytest.mark.asyncio()
    async def test_consumer_without_producer_continues_normally(self):
        """Testa que consumer funciona normalmente sem producer."""
        # Setup mock generator
        mock_result = MagicMock()
        mock_result.total_tests_generated = 3
        mock_result.test_suite.id = "TS-NO-PRODUCER"
        mock_result.test_suite.test_cases = []

        mock_generator = AsyncMock()
        mock_generator.generate_tests = AsyncMock(return_value=mock_result)

        # Criar consumer SEM producer
        consumer = RequirementsConsumer(
            test_generator=mock_generator,
            producer=None,
        )

        # Preparar mensagem
        test_msg = MagicMock()
        test_msg.topic = "requirements.generated"
        test_msg.offset = 101
        test_msg.key = b"no-producer"
        test_msg.value = json.dumps(
            {
                "requirements_set_id": "REQ-SET-NO-PROD",
                "plan_id": "plan-no-prod",
                "requirements": [
                    {
                        "id": "REQ-NO-PROD-001",
                        "title": "No Producer Test",
                        "description": "Test without producer",
                    }
                ],
            }
        ).encode("utf-8")

        # Processar mensagem - não deve lançar erro
        await consumer._process_message(test_msg)

        # Verificar que testes foram gerados
        mock_generator.generate_tests.assert_called_once()
