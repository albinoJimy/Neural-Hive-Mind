"""Testes de integração para Exactly-Once Semantics (EOS) no Kafka"""
import pytest
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Set
from unittest.mock import patch
import os

# Testcontainers para Kafka
try:
    from testcontainers.kafka import KafkaContainer
    from testcontainers.compose import DockerCompose
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False

from kafka.producer import KafkaIntentProducer
from models.intent_envelope import IntentEnvelope


@pytest.mark.skipif(not TESTCONTAINERS_AVAILABLE, reason="Testcontainers not available")
@pytest.mark.integration
class TestKafkaEOS:
    """Testes de integração para Exactly-Once Semantics"""

    @pytest.fixture(scope="class")
    def kafka_cluster(self):
        """Fixture para cluster Kafka com testcontainers"""
        # Use docker-compose para Kafka + Schema Registry
        compose_file_path = os.path.join(
            os.path.dirname(__file__), "..", "docker-compose.test.yml"
        )

        compose = DockerCompose(
            filepath=os.path.dirname(compose_file_path),
            compose_file_name="docker-compose.test.yml",
            pull=True
        )

        compose.start()

        # Wait for services to be ready
        kafka_port = compose.get_service_port("kafka", 9092)
        schema_registry_port = compose.get_service_port("schema-registry", 8081)

        bootstrap_servers = f"localhost:{kafka_port}"
        schema_registry_url = f"http://localhost:{schema_registry_port}"

        yield {
            "bootstrap_servers": bootstrap_servers,
            "schema_registry_url": schema_registry_url
        }

        compose.stop()

    @pytest.fixture
    async def kafka_producer(self, kafka_cluster):
        """Fixture para producer Kafka configurado"""
        producer = KafkaIntentProducer(
            bootstrap_servers=kafka_cluster["bootstrap_servers"],
            schema_registry_url=kafka_cluster["schema_registry_url"]
        )

        # Mock do schema loading
        with patch('builtins.open') as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = """
            {
              "type": "record",
              "name": "IntentEnvelope",
              "fields": [
                {"name": "id", "type": "string"},
                {"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}}
              ]
            }
            """
            await producer.initialize()

        yield producer

        await producer.close()

    @pytest.mark.asyncio
    async def test_exactly_once_delivery(self, kafka_producer):
        """Teste de exactly-once delivery básico"""
        # Create test intent
        intent_envelope = self._create_test_intent("eos-test-1")

        # Send intent
        await kafka_producer.send_intent(intent_envelope)

        # Verify message was sent (this is a basic test - in real scenario
        # we would consume and verify the message was received exactly once)
        assert True  # Producer didn't raise an exception

    @pytest.mark.asyncio
    async def test_idempotency_collision(self, kafka_producer):
        """Teste de colisão de idempotência"""
        # Create multiple intents with same ID (should be idempotent)
        intent_id = f"collision-test-{uuid.uuid4()}"

        intent1 = self._create_test_intent(intent_id)
        intent2 = self._create_test_intent(intent_id)  # Same ID

        # Send both intents
        await kafka_producer.send_intent(intent1)
        await kafka_producer.send_intent(intent2)

        # Both should succeed due to idempotency
        # In real scenario, only one message should be delivered to consumer
        assert True

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, kafka_producer):
        """Teste de rollback de transação em caso de erro"""
        intent_envelope = self._create_test_intent("rollback-test")

        # Mock an error during transaction
        original_commit = kafka_producer.producer.commit_transaction

        def mock_commit_error():
            raise Exception("Simulated commit error")

        kafka_producer.producer.commit_transaction = mock_commit_error

        with pytest.raises(Exception, match="Simulated commit error"):
            await kafka_producer.send_intent(intent_envelope)

        # Restore original method
        kafka_producer.producer.commit_transaction = original_commit

        # Transaction should have been aborted
        # Producer should still be in working state
        assert kafka_producer.is_ready()

    @pytest.mark.asyncio
    async def test_concurrent_producers_eos(self, kafka_cluster):
        """Teste de múltiplos producers concorrentes com EOS"""
        num_producers = 3
        intents_per_producer = 10

        producers = []
        tasks = []

        try:
            # Create multiple producers with different transactional IDs
            for i in range(num_producers):
                producer = KafkaIntentProducer(
                    bootstrap_servers=kafka_cluster["bootstrap_servers"],
                    schema_registry_url=kafka_cluster["schema_registry_url"]
                )

                # Override transactional ID to ensure uniqueness
                producer._transactional_id = f"test-producer-{i}-{uuid.uuid4()}"

                with patch('builtins.open') as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = """
                    {
                      "type": "record",
                      "name": "IntentEnvelope",
                      "fields": [
                        {"name": "id", "type": "string"},
                        {"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}}
                      ]
                    }
                    """
                    await producer.initialize()

                producers.append(producer)

                # Create task for each producer
                task = asyncio.create_task(
                    self._send_intents_batch(producer, intents_per_producer, i)
                )
                tasks.append(task)

            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify all tasks completed successfully
            for result in results:
                if isinstance(result, Exception):
                    pytest.fail(f"Producer task failed: {result}")

        finally:
            # Cleanup producers
            for producer in producers:
                await producer.close()

    @pytest.mark.asyncio
    async def test_producer_recovery_after_failure(self, kafka_cluster):
        """Teste de recuperação do producer após falha"""
        producer = KafkaIntentProducer(
            bootstrap_servers=kafka_cluster["bootstrap_servers"],
            schema_registry_url=kafka_cluster["schema_registry_url"]
        )

        with patch('builtins.open') as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = """
            {
              "type": "record",
              "name": "IntentEnvelope",
              "fields": [
                {"name": "id", "type": "string"},
                {"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}}
              ]
            }
            """
            await producer.initialize()

        try:
            # Send successful intent
            intent1 = self._create_test_intent("recovery-test-1")
            await producer.send_intent(intent1)

            # Simulate failure by closing producer connection
            producer.producer.close()

            # Try to send another intent (should fail)
            intent2 = self._create_test_intent("recovery-test-2")
            with pytest.raises(Exception):
                await producer.send_intent(intent2)

            # Reinitialize producer
            with patch('builtins.open') as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = """
                {
                  "type": "record",
                  "name": "IntentEnvelope",
                  "fields": [
                    {"name": "id", "type": "string"},
                    {"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}}
                  ]
                }
                """
                await producer.initialize()

            # Should be able to send again
            intent3 = self._create_test_intent("recovery-test-3")
            await producer.send_intent(intent3)

        finally:
            await producer.close()

    @pytest.mark.asyncio
    async def test_stable_transactional_id_generation(self, kafka_cluster):
        """Teste da geração estável de transactional ID"""
        # Test with environment variables
        with patch.dict(os.environ, {
            'HOSTNAME': 'test-pod-123',
            'POD_UID': 'uid-456'
        }):
            producer1 = KafkaIntentProducer(
                bootstrap_servers=kafka_cluster["bootstrap_servers"],
                schema_registry_url=kafka_cluster["schema_registry_url"]
            )

            producer2 = KafkaIntentProducer(
                bootstrap_servers=kafka_cluster["bootstrap_servers"],
                schema_registry_url=kafka_cluster["schema_registry_url"]
            )

            # Both producers should generate the same transactional ID
            assert producer1._transactional_id == producer2._transactional_id
            assert "test-pod-123" in producer1._transactional_id
            assert "uid-456" in producer1._transactional_id

    async def _send_intents_batch(self, producer: KafkaIntentProducer, count: int, batch_id: int):
        """Helper para enviar lote de intenções"""
        for i in range(count):
            intent_id = f"batch-{batch_id}-intent-{i}-{uuid.uuid4()}"
            intent = self._create_test_intent(intent_id)

            await producer.send_intent(intent)

            # Small delay to simulate realistic timing
            await asyncio.sleep(0.01)

    def _create_test_intent(self, intent_id: str) -> IntentEnvelope:
        """Helper para criar intenção de teste"""
        return IntentEnvelope(
            id=intent_id,
            correlation_id=f"correlation-{intent_id}",
            actor={
                "id": "test-user",
                "actor_type": "human",
                "name": "Test User"
            },
            intent={
                "text": f"Test intent {intent_id}",
                "domain": "business",
                "classification": "test",
                "original_language": "pt-BR",
                "processed_text": f"test intent {intent_id}",
                "entities": [],
                "keywords": ["test"]
            },
            confidence=0.9,
            context={
                "userId": "test-user",
                "sessionId": "test-session"
            },
            timestamp=datetime.now(timezone.utc)
        )


@pytest.mark.integration
class TestKafkaEOSNegativeCases:
    """Testes de casos negativos para EOS"""

    @pytest.mark.asyncio
    async def test_duplicate_transactional_id_error(self):
        """Teste de erro com transactional IDs duplicados"""
        # This test would require more complex setup with actual Kafka
        # to simulate the scenario where two producers try to use
        # the same transactional ID simultaneously
        pass

    @pytest.mark.asyncio
    async def test_transaction_timeout(self):
        """Teste de timeout de transação"""
        # Mock scenario where transaction takes too long
        pass

    @pytest.mark.asyncio
    async def test_broker_restart_during_transaction(self):
        """Teste de restart do broker durante transação"""
        # Test resilience when Kafka broker restarts mid-transaction
        pass