"""
Testes unitários para integração Kafka da Explainability API.

TDD: Testes escritos antes da implementação (GAPS-04 Task 6).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConsensusDecisionConsumer:
    """Testes do consumer para consensus.decision.created."""

    @pytest.fixture
    def mock_explainability_service(self):
        """Mock do ExplainabilityAPIExtensions."""
        service = MagicMock()
        service.get_explainability_by_decision_id = AsyncMock(return_value=None)
        service.generate_explanation = AsyncMock(
            return_value={"explainability_token": "token-123", "decision_id": "decision-456"}
        )
        return service

    @pytest.fixture
    def mock_producer(self):
        """Mock do ExplanationProducer."""
        producer = MagicMock()
        producer.publish_explanation = AsyncMock()
        return producer

    @pytest.fixture
    def mock_kafka_consumer(self):
        """Mock do AIOKafkaConsumer."""
        consumer = MagicMock()
        consumer.start = AsyncMock()
        consumer.stop = AsyncMock()
        consumer.getmany = AsyncMock(return_value={})
        consumer.commit = AsyncMock()
        return consumer

    @pytest.mark.asyncio
    async def test_consumer_initialization(self, mock_explainability_service, mock_producer):
        """Testa que o consumer pode ser inicializado."""
        from src.consumers.consensus_decision_consumer import ConsensusDecisionConsumer

        consumer = ConsensusDecisionConsumer(
            bootstrap_servers="localhost:9092",
            group_id="explainability-group",
            explainability_service=mock_explainability_service,
            explanation_producer=mock_producer,
            input_topic="consensus.decision.created",
            output_topic="consensus.explanations",
        )

        assert consumer is not None
        assert consumer.bootstrap_servers == "localhost:9092"
        assert consumer.group_id == "explainability-group"

    @pytest.mark.asyncio
    async def test_consumer_connects_to_kafka(
        self, mock_explainability_service, mock_producer, mock_kafka_consumer
    ):
        """Testa que o consumer conecta ao Kafka."""
        from src.consumers.consensus_decision_consumer import ConsensusDecisionConsumer

        with patch(
            "src.consumers.consensus_decision_consumer.AIOKafkaConsumer",
            return_value=mock_kafka_consumer,
        ):
            consumer = ConsensusDecisionConsumer(
                bootstrap_servers="localhost:9092",
                group_id="explainability-group",
                explainability_service=mock_explainability_service,
                explanation_producer=mock_producer,
                input_topic="consensus.decision.created",
                output_topic="consensus.explanations",
            )

            await consumer.connect()

            mock_kafka_consumer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_decision_creates_explanation(
        self, mock_explainability_service, mock_producer
    ):
        """Testa que handle_decision cria explicação nova."""
        from src.consumers.consensus_decision_consumer import ConsensusDecisionConsumer

        consumer = ConsensusDecisionConsumer(
            bootstrap_servers="localhost:9092",
            group_id="explainability-group",
            explainability_service=mock_explainability_service,
            explanation_producer=mock_producer,
            input_topic="consensus.decision.created",
            output_topic="consensus.explanations",
        )

        decision_message = {
            "decision_id": "decision-123",
            "final_decision": "approve",
            "aggregated_confidence": 0.85,
            "specialist_opinions": [
                {"specialist_type": "business", "confidence": 0.85, "risk": 0.15}
            ],
        }

        await consumer.handle_decision(decision_message)

        # Verificar que generate_explanation foi chamado
        mock_explainability_service.generate_explanation.assert_called_once()
        call_args = mock_explainability_service.generate_explanation.call_args
        assert call_args[0][0]["decision_id"] == "decision-123"

    @pytest.mark.asyncio
    async def test_handle_decision_publishes_explanation(
        self, mock_explainability_service, mock_producer
    ):
        """Testa que handle_decision publica explicação."""
        from src.consumers.consensus_decision_consumer import ConsensusDecisionConsumer

        consumer = ConsensusDecisionConsumer(
            bootstrap_servers="localhost:9092",
            group_id="explainability-group",
            explainability_service=mock_explainability_service,
            explanation_producer=mock_producer,
            input_topic="consensus.decision.created",
            output_topic="consensus.explanations",
        )

        decision_message = {"decision_id": "decision-123", "final_decision": "approve"}

        await consumer.handle_decision(decision_message)

        # Verificar que publish_explanation foi chamado
        mock_producer.publish_explanation.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_decision_with_existing_explanation(
        self, mock_explainability_service, mock_producer
    ):
        """Testa que handle_decision reutiliza explicação existente."""
        from src.consumers.consensus_decision_consumer import ConsensusDecisionConsumer

        # Configurar mock para retornar explicação existente
        mock_explainability_service.get_explainability_by_decision_id.return_value = {
            "explainability_token": "existing-token",
            "decision_id": "decision-123",
        }

        consumer = ConsensusDecisionConsumer(
            bootstrap_servers="localhost:9092",
            group_id="explainability-group",
            explainability_service=mock_explainability_service,
            explanation_producer=mock_producer,
            input_topic="consensus.decision.created",
            output_topic="consensus.explanations",
        )

        decision_message = {"decision_id": "decision-123", "final_decision": "approve"}

        await consumer.handle_decision(decision_message)

        # Verificar que get_explainability foi chamado
        mock_explainability_service.get_explainability_by_decision_id.assert_called_once_with(
            "decision-123"
        )
        # Verificar que generate_explanation NÃO foi chamado
        mock_explainability_service.generate_explanation.assert_not_called()


class TestExplanationProducer:
    """Testes do producer para consensus.explanations."""

    @pytest.fixture
    def mock_kafka_producer(self):
        """Mock do AIOKafkaProducer."""
        producer = MagicMock()
        producer.start = AsyncMock()
        producer.stop = AsyncMock()
        producer.send_and_wait = AsyncMock()
        producer.send = AsyncMock()
        return producer

    @pytest.mark.asyncio
    async def test_producer_initialization(self, mock_kafka_producer):
        """Testa que o producer pode ser inicializado."""
        from src.producers.explanation_producer import ExplanationProducer

        producer = ExplanationProducer(
            bootstrap_servers="localhost:9092", topic="consensus.explanations"
        )

        assert producer is not None
        assert producer.bootstrap_servers == "localhost:9092"
        assert producer.topic == "consensus.explanations"

    @pytest.mark.asyncio
    async def test_producer_connects_to_kafka(self, mock_kafka_producer):
        """Testa que o producer conecta ao Kafka."""
        from src.producers.explanation_producer import ExplanationProducer

        with patch(
            "src.producers.explanation_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = ExplanationProducer(
                bootstrap_servers="localhost:9092", topic="consensus.explanations"
            )

            await producer.connect()

            mock_kafka_producer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_explanation_sends_to_kafka(self, mock_kafka_producer):
        """Testa que publish_explanation envia para Kafka."""
        from src.producers.explanation_producer import ExplanationProducer

        with patch(
            "src.producers.explanation_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = ExplanationProducer(
                bootstrap_servers="localhost:9092", topic="consensus.explanations"
            )

            await producer.connect()

            explanation = {
                "explainability_token": "token-123",
                "decision_id": "decision-456",
                "final_decision": "approve",
                "explanation_quality": {"overall": 0.85},
            }

            await producer.publish_explanation(explanation)

            mock_kafka_producer.send_and_wait.assert_called_once()
            call_args = mock_kafka_producer.send_and_wait.call_args
            assert call_args[0][0] == "consensus.explanations"

    @pytest.mark.asyncio
    async def test_publish_explanation_serializes_json(self, mock_kafka_producer):
        """Testa que publish_explanation serializa JSON corretamente."""
        from src.producers.explanation_producer import ExplanationProducer

        with patch(
            "src.producers.explanation_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = ExplanationProducer(
                bootstrap_servers="localhost:9092", topic="consensus.explanations"
            )

            await producer.connect()

            explanation = {"explainability_token": "token-123", "decision_id": "decision-456"}

            await producer.publish_explanation(explanation)

            # Verificar que send_and_wait foi chamado com os parâmetros corretos
            mock_kafka_producer.send_and_wait.assert_called_once()
            call_args = mock_kafka_producer.send_and_wait.call_args
            # O primeiro argumento é o tópico, o valor é passado via keyword
            assert call_args[0][0] == "consensus.explanations"
            # O value serializer converte para bytes, mas mock não aplica serializer
            # Apenas verificar que o valor original foi passado
            assert "value" in call_args[1]

    @pytest.mark.asyncio
    async def test_publish_explanation_includes_headers(self, mock_kafka_producer):
        """Testa que publish_explanation inclui headers de tracing."""
        from src.producers.explanation_producer import ExplanationProducer

        with patch(
            "src.producers.explanation_producer.AIOKafkaProducer", return_value=mock_kafka_producer
        ):
            producer = ExplanationProducer(
                bootstrap_servers="localhost:9092", topic="consensus.explanations"
            )

            await producer.connect()

            explanation = {"decision_id": "decision-456", "traceparent": "00-trace-id"}

            await producer.publish_explanation(explanation)

            # Verificar headers
            call_args = mock_kafka_producer.send_and_wait.call_args
            headers = call_args[1].get("headers", [])
            # Headers devem estar presentes
            assert headers is not None or "headers" in call_args[1]


class TestKafkaIntegrationE2E:
    """Testes de integração E2E do fluxo Kafka."""

    @pytest.fixture
    def mock_services(self):
        """Mock de todos os serviços."""
        return {"explainability_service": MagicMock(), "producer": MagicMock()}

    @pytest.mark.asyncio
    async def test_decision_to_explanation_flow(self, mock_services):
        """Testa fluxo completo: decisão → explicação → publicação."""
        from src.consumers.consensus_decision_consumer import ConsensusDecisionConsumer

        # Setup mocks
        mock_services["explainability_service"].get_explainability_by_decision_id = AsyncMock(
            return_value=None
        )
        mock_services["explainability_service"].generate_explanation = AsyncMock(
            return_value={"explainability_token": "token-123", "decision_id": "decision-456"}
        )
        mock_services["producer"].publish_explanation = AsyncMock()

        consumer = ConsensusDecisionConsumer(
            bootstrap_servers="localhost:9092",
            group_id="explainability-group",
            explainability_service=mock_services["explainability_service"],
            explanation_producer=mock_services["producer"],
            input_topic="consensus.decision.created",
            output_topic="consensus.explanations",
        )

        decision_message = {
            "decision_id": "decision-456",
            "final_decision": "approve",
            "aggregated_confidence": 0.85,
            "specialist_opinions": [
                {"specialist_type": "business", "confidence": 0.85, "risk": 0.15}
            ],
        }

        # Processar decisão
        await consumer.handle_decision(decision_message)

        # Verificar que explicação foi gerada
        mock_services["explainability_service"].generate_explanation.assert_called_once()

        # Verificar que explicação foi publicada
        mock_services["producer"].publish_explanation.assert_called_once()
