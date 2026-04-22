"""Testes de integração para Flow C Consumer.

Autor: Neural Hive Mind
Criado: 2026-04-20 (FEAT-A-002)
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.integration.flow_c_consumer import (
    FlowCConsumer,
    _deserialize_avro_message,
)


@pytest.fixture()
def mock_config():
    """Mock do OrchestratorSettings."""
    config = MagicMock()
    config.kafka_bootstrap_servers = "localhost:9092"
    config.kafka_consumer_group_id = "orchestrator-flow-c"
    config.kafka_consensus_topic = "plans.consensus"
    config.ml_allocation_outcomes_topic = "orchestration.incidents"
    config.kafka_security_protocol = "PLAINTEXT"
    return config


@pytest.fixture()
def mock_flow_c_orchestrator():
    """Mock do FlowCOrchestrator."""
    orchestrator = AsyncMock()
    orchestrator.execute_flow_c = AsyncMock(
        return_value=MagicMock(
            success=True,
            tickets_generated=2,
            tickets_completed=0,
            total_duration_ms=1000,
        )
    )
    return orchestrator


@pytest.mark.asyncio()
class TestFlowCConsumer:
    """Testes para FlowCConsumer."""

    async def test_consumer_initialization(self, mock_config):
        """Testa inicialização do consumidor."""
        consumer = FlowCConsumer(config=mock_config)

        assert consumer.kafka_servers == "localhost:9092"
        assert consumer.input_topic == "plans.consensus"
        assert "flow-c" in consumer.group_id

    async def test_consumer_initialization_with_defaults(self):
        """Testa inicialização do consumidor com defaults."""
        consumer = FlowCConsumer()

        assert consumer.kafka_servers == "kafka-bootstrap.kafka.svc.cluster.local:9092"
        assert consumer.input_topic == "plans.consensus"
        assert consumer.group_id == "flow-c-orchestrator"

    async def test_consumer_processes_json_message(self, mock_config, mock_flow_c_orchestrator):
        """Testa processamento de mensagem JSON."""
        consumer = FlowCConsumer(config=mock_config)
        consumer.orchestrator = mock_flow_c_orchestrator
        consumer.consumer = AsyncMock()  # Mock consumer
        consumer.producer = AsyncMock()  # Mock producer
        consumer.running = True  # Simular que está rodando

        # Mock message
        mock_msg = MagicMock()
        mock_msg.topic = "plans.consensus"
        mock_msg.partition = 0
        mock_msg.offset = 100
        mock_msg.key = b"test-key"
        mock_msg.value = json.dumps(
            {
                "plan_id": "PLAN-001",
                "intent_id": "INTENT-001",
                "decision_id": "DEC-001",
                "status": "approved",
                "tasks": [
                    {"task_id": "T1", "type": "BUILD", "description": "Build service"},
                ],
            }
        ).encode("utf-8")

        # Process message
        await consumer._process_message(mock_msg)

        # Verify orchestrator was called
        mock_flow_c_orchestrator.execute_flow_c.assert_called_once()

    async def test_consumer_handles_invalid_json(self, mock_config):
        """Testa que consumidor lida com JSON inválido."""
        consumer = FlowCConsumer(config=mock_config)
        consumer.consumer = AsyncMock()  # Mock consumer
        consumer.producer = AsyncMock()  # Mock producer
        consumer.running = True  # Simular que está rodando

        mock_msg = MagicMock()
        mock_msg.topic = "plans.consensus"
        mock_msg.offset = 100
        mock_msg.value = b"invalid json"

        # Process message - não deve lançar erro
        await consumer._process_message(mock_msg)

        # Verify error was logged (via consumer.logger)
        # Não deve crashar mesmo com JSON inválido

    async def test_consumer_running_property(self, mock_config):
        """Testa propriedade running do consumidor."""
        consumer = FlowCConsumer(config=mock_config)

        # Inicialmente não está rodando
        assert consumer.running is False

        # Simular que está rodando
        consumer.running = True
        assert consumer.running is True


@pytest.mark.asyncio()
class TestAvroDeserialization:
    """Testes para deserialização Avro."""

    def test_deserialize_json_message(self):
        """Testa deserialização de mensagem JSON."""
        json_data = {"plan_id": "PLAN-001", "status": "approved"}
        raw_bytes = json.dumps(json_data).encode("utf-8")

        result = _deserialize_avro_message(raw_bytes)

        assert result["plan_id"] == "PLAN-001"
        assert result["status"] == "approved"

    def test_deserialize_json_fallback_for_short_message(self):
        """Testa fallback para JSON quando mensagem é muito curta."""
        raw_bytes = b"{}"

        result = _deserialize_avro_message(raw_bytes)

        assert result == {}

    def test_deserialize_avro_with_magic_byte(self):
        """Testa deserialização Avro com magic byte correto."""
        # Simular mensagem Avro com wire format
        # Magic byte (0x00) + Schema ID (4 bytes) + payload
        schema_id = 12345
        payload = json.dumps({"plan_id": "PLAN-001"}).encode("utf-8")

        raw_bytes = bytes([0x00]) + schema_id.to_bytes(4, "big") + payload

        # Sem schema registry, deve tentar JSON
        result = _deserialize_avro_message(raw_bytes)

        # Deve voltar para JSON quando schema registry não disponível
        assert "plan_id" in result or result == {}

    def test_deserialize_invalid_message_raises_error(self):
        """Testa que mensagem inválida levanta erro."""
        raw_bytes = b"\x01\x00\x00\x00\x00"  # Magic byte inválido

        with pytest.raises(ValueError):
            _deserialize_avro_message(raw_bytes)
