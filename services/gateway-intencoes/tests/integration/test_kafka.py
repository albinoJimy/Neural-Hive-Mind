"""
Integration tests para Kafka communication.

Testa comunicação básica com Kafka: produtor, tópicos e envio de mensagens.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from confluent_kafka import KafkaException


@pytest.mark.asyncio
class TestKafkaProducerConnection:
    """Testa conexão do produtor Kafka."""

    async def test_kafka producer_initialization(self):
        """Testa que produtor Kafka pode ser inicializado."""
        from src.kafka.producer import KafkaIntentProducer
        from src.config.settings import get_settings

        settings = get_settings()

        # Mock do produtor Kafka para evitar conexão real
        with patch("src.kafka.producer.SerializingProducer") as mock_producer_class:
            mock_producer = MagicMock()
            mock_producer_class.return_value = mock_producer

            producer = KafkaIntentProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                schema_registry_url=settings.schema_registry_url,
            )

            assert producer is not None
            assert producer.bootstrap_servers == settings.kafka_bootstrap_servers

    async def test_kafka_send_intent_success(self):
        """Testa envio de intent para Kafka com sucesso."""
        from src.kafka.producer import KafkaIntentProducer
        from src.models.intent_envelope import IntentEnvelope

        # Mock do produtor Kafka
        with patch("src.kafka.producer.SerializingProducer") as mock_producer_class:
            mock_producer = MagicMock()
            mock_producer_class.return_value = mock_producer

            producer = KafkaIntentProducer(
                bootstrap_servers="localhost:9092",
                schema_registry_url="http://localhost:8081",
            )

            # Criar intent de teste
            intent = IntentEnvelope(
                intent_id="test-intent-123",
                text="Testar comunicação Kafka",
                domain="test",
                confidence=0.9,
                user_id="test-user",
                tenant_id="test-tenant",
            )

            # Mock delivery callback
            producer.produce = MagicMock()

            # Enviar intent
            await producer.publish_intent(
                intent=intent,
                topic="intentions.test",
            )

            # Verificar que producer.produce foi chamado
            assert producer.produce.called

    async def test_kafka_send_intent_failure(self):
        """Testa falha ao enviar intent para Kafka."""
        from src.kafka.producer import KafkaIntentProducer
        from src.models.intent_envelope import IntentEnvelope

        # Mock do produtor Kafka que levanta exceção
        with patch("src.kafka.producer.SerializingProducer") as mock_producer_class:
            mock_producer = MagicMock()
            mock_producer.produce = MagicMock(side_effect=KafkaException("Kafka error"))
            mock_producer_class.return_value = mock_producer

            producer = KafkaIntentProducer(
                bootstrap_servers="localhost:9092",
                schema_registry_url="http://localhost:8081",
            )

            # Criar intent de teste
            intent = IntentEnvelope(
                intent_id="test-intent-456",
                text="Testar falha Kafka",
                domain="test",
                confidence=0.9,
                user_id="test-user",
                tenant_id="test-tenant",
            )

            # Enviar deve falhar mas não levantar exceção (logger captura)
            await producer.publish_intent(
                intent=intent,
                topic="intentions.test",
            )

            # Verificar que producer.produce foi chamado
            assert producer.produce.called


@pytest.mark.asyncio
class TestKafkaTopicsConfiguration:
    """Testa configuração de tópicos Kafka."""

    def test_gateway_topics_prefix(self):
        """Testa que GatewayTopics tem PREFIX correto."""
        from src.config.settings import GatewayTopics

        topics = GatewayTopics()
        assert topics.PREFIX == "gateway"

    def test_gateway_topics_domain_topic(self):
        """Testa geração de tópico por domínio."""
        from src.config.settings import GatewayTopics

        topics = GatewayTopics()
        business_topic = topics.get_domain_topic("business")
        technical_topic = topics.get_domain_topic("technical")

        assert business_topic == "intentions.business"
        assert technical_topic == "intentions.technical"

    def test_gateway_topics_dlq_topic(self):
        """Testa geração de tópico DLQ por domínio."""
        from src.config.settings import GatewayTopics

        topics = GatewayTopics()
        business_dlq = topics.get_dlq_topic("business")
        technical_dlq = topics.get_dlq_topic("technical")

        assert business_dlq == "dlq.intentions.business"
        assert technical_dlq == "dlq.intentions.technical"

    def test_gateway_topics_all_topics_mapping(self):
        """Testa mapeamento completo de tópicos."""
        from src.config.settings import GatewayTopics

        topics = GatewayTopics()
        all_topics = topics.get_all_topics()

        assert "intentions_business" in all_topics
        assert "intentions_technical" in all_topics
        assert "intentions_behavior" in all_topics
        assert "dlq_business" in all_topics
        assert "dlq_technical" in all_topics

        assert all_topics["intentions_business"] == "intentions.business"
        assert all_topics["dlq_business"] == "dlq.intentions.business"


@pytest.mark.asyncio
class TestKafkaConsumer:
    """Testa consumidor Kafka básico."""

    async def test_kafka_consumer_initialization(self):
        """Testa que consumidor Kafka pode ser inicializado."""
        from src.kafka.consumer import KafkaIntentConsumer

        # Mock do consumidor Kafka
        with patch("src.kafka.consumer.DeserializingConsumer") as mock_consumer_class:
            mock_consumer = MagicMock()
            mock_consumer_class.return_value = mock_consumer

            consumer = KafkaIntentConsumer(
                bootstrap_servers="localhost:9092",
                group_id="test-group",
                topics=["intentions.test"],
            )

            assert consumer is not None
            assert consumer.group_id == "test-group"
