"""
Unit tests para InsightsConsumer.

Testa o consumer que processa insights.analyzed do Analyst Agents,
enriquecendo Cognitive Plans e armazenando insights para histórico.
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Mock de dependências problemáticas antes de importar
sys.modules["neural_hive_security"] = MagicMock()
sys.modules["neural_hive_security.cors"] = MagicMock()

from src.consumers.insights_consumer import InsightsConsumer


@pytest.fixture()
def mock_config():
    """Config mock para testes."""
    config = MagicMock()
    config.kafka_bootstrap_servers = "localhost:9092"
    config.kafka_consumer_group_id = "test-group"
    config.kafka_insights_topic = "insights.analyzed"
    config.kafka_security_protocol = "PLAINTEXT"
    return config


@pytest.fixture()
def mock_mongodb_client():
    """MongoDB client mock."""
    mongodb = AsyncMock()
    return mongodb


@pytest.fixture()
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock()
    metrics.insights_consumed_total = MagicMock()
    metrics.insights_consumed_total.labels.return_value = MagicMock()
    metrics.insights_consumed_total.labels.return_value.inc = MagicMock()
    return metrics


@pytest.fixture()
def consumer(mock_config, mock_mongodb_client, mock_metrics):
    """Consumer instance para testes."""
    return InsightsConsumer(
        config=mock_config, mongodb_client=mock_mongodb_client, metrics=mock_metrics
    )


class TestInsightsConsumerInitialization:
    """Testes de inicialização do consumer."""

    def test_consumer_initialization(self, consumer):
        """Consumer deve ter atributos corretos após criação."""
        assert consumer.config is not None
        assert consumer.mongodb_client is not None
        assert consumer.metrics is not None
        assert consumer.consumer is None  # Não inicializado automaticamente
        assert consumer.running is False

    @pytest.mark.asyncio()
    async def test_consumer_initialize(self, consumer):
        """Consumer deve inicializar corretamente."""
        mock_producer = MagicMock()
        mock_producer.start = AsyncMock()

        with patch("src.consumers.insights_consumer.instrument_kafka_consumer") as mock_instrument:
            mock_instrument.return_value = mock_producer

            await consumer.initialize()

            assert consumer.consumer is not None
            mock_producer.start.assert_called_once()


class TestProcessMessage:
    """Testes de processamento de mensagens."""

    @pytest.mark.asyncio()
    async def test_process_high_priority_insight(self, consumer, mock_mongodb_client):
        """Deve processar insight de alta prioridade."""
        insight_data = {
            "insight_id": "insight-123",
            "insight_type": "PREDICTIVE",
            "priority": "HIGH",
            "plan_id": "plan-456",
            "correlation_id": "corr-789",
            "description": "Test insight",
            "recommendations": ["action1", "action2"],
        }

        message = MagicMock()
        message.value = json.dumps(insight_data).encode("utf-8")
        message.headers = []
        message.topic = "insights.analyzed"
        message.partition = 0
        message.offset = 0

        # Mock MongoDB
        mock_mongodb_client.get_cognitive_plan = AsyncMock(
            return_value={"plan_id": "plan-456", "status": "IN_PROGRESS", "insights": []}
        )
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_insight = AsyncMock()

        # Mock commit
        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar que o plano foi enriquecido
        mock_mongodb_client.update_cognitive_plan.assert_called_once()
        call_args = mock_mongodb_client.update_cognitive_plan.call_args
        assert call_args.kwargs["plan_id"] == "plan-456"
        assert "insights" in call_args.kwargs["updates"]

        # Verificar que insight foi armazenado
        mock_mongodb_client.insert_insight.assert_called_once()

    @pytest.mark.asyncio()
    async def test_filter_low_priority_insight(self, consumer, mock_mongodb_client):
        """Deve filtrar insight de baixa prioridade."""
        insight_data = {
            "insight_id": "insight-123",
            "insight_type": "OPERATIONAL",
            "priority": "MEDIUM",  # Baixa prioridade
            "plan_id": "plan-456",
            "description": "Test insight",
        }

        message = MagicMock()
        message.value = json.dumps(insight_data).encode("utf-8")
        message.headers = []

        # Mock MongoDB
        mock_mongodb_client.get_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_insight = AsyncMock()

        await consumer._process_message(message)

        # Verificar que NÃO chamou MongoDB (filtro por prioridade)
        mock_mongodb_client.get_cognitive_plan.assert_not_called()
        mock_mongodb_client.insert_insight.assert_not_called()

    @pytest.mark.asyncio()
    async def test_process_insight_without_plan(self, consumer, mock_mongodb_client):
        """Deve processar insight sem plan_id (apenas armazenar)."""
        insight_data = {
            "insight_id": "insight-123",
            "insight_type": "PREDICTIVE",
            "priority": "HIGH",
            # Sem plan_id
            "description": "Test insight",
        }

        message = MagicMock()
        message.value = json.dumps(insight_data).encode("utf-8")
        message.headers = []

        # Mock MongoDB
        mock_mongodb_client.get_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_insight = AsyncMock()

        await consumer._process_message(message)

        # Deve armazenar mesmo sem plan_id
        mock_mongodb_client.insert_insight.assert_called_once()

    @pytest.mark.asyncio()
    async def test_skip_insight_for_completed_plan(self, consumer, mock_mongodb_client):
        """Deve ignorar insight para plano já completado."""
        insight_data = {
            "insight_id": "insight-123",
            "insight_type": "PREDICTIVE",
            "priority": "HIGH",
            "plan_id": "plan-456",
            "description": "Test insight",
        }

        message = MagicMock()
        message.value = json.dumps(insight_data).encode("utf-8")
        message.headers = []

        # Mock MongoDB retorna plano completado
        mock_mongodb_client.get_cognitive_plan = AsyncMock(
            return_value={"plan_id": "plan-456", "status": "COMPLETED"}  # Plano já finalizado
        )
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_insight = AsyncMock()

        await consumer._process_message(message)

        # Não deve atualizar plano completado
        mock_mongodb_client.update_cognitive_plan.assert_not_called()

    @pytest.mark.asyncio()
    async def test_prevent_duplicate_insights(self, consumer, mock_mongodb_client):
        """Deve prevenir duplicação de insights no plano."""
        insight_data = {
            "insight_id": "insight-123",
            "insight_type": "PREDICTIVE",
            "priority": "HIGH",
            "plan_id": "plan-456",
            "description": "Test insight",
        }

        message = MagicMock()
        message.value = json.dumps(insight_data).encode("utf-8")
        message.headers = []

        # Mock MongoDB retorna plano com insight já existente
        existing_insight = {
            "insight_id": "insight-123",  # Mesmo ID
            "description": "Existing insight",
        }

        mock_mongodb_client.get_cognitive_plan = AsyncMock(
            return_value={
                "plan_id": "plan-456",
                "status": "IN_PROGRESS",
                "insights": [existing_insight],
            }
        )
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_insight = AsyncMock()

        await consumer._process_message(message)

        # Não deve adicionar duplicata
        mock_mongodb_client.update_cognitive_plan.assert_not_called()


class TestEnrichCognitivePlan:
    """Testes de enriquecimento de Cognitive Plan."""

    @pytest.mark.asyncio()
    async def test_enrich_plan_with_insight(self, consumer, mock_mongodb_client):
        """Deve enriquecer plano com insight."""
        insight = {
            "insight_id": "insight-123",
            "insight_type": "PREDICTIVE",
            "priority": "HIGH",
            "plan_id": "plan-456",
            "description": "Test insight",
            "recommendations": ["action1"],
        }

        mock_mongodb_client.get_cognitive_plan = AsyncMock(
            return_value={"plan_id": "plan-456", "status": "IN_PROGRESS", "insights": []}
        )
        mock_mongodb_client.update_cognitive_plan = AsyncMock()

        await consumer._enrich_cognitive_plan(insight)

        # Verificar chamada
        mock_mongodb_client.update_cognitive_plan.assert_called_once()
        call_args = mock_mongodb_client.update_cognitive_plan.call_args
        assert call_args.kwargs["plan_id"] == "plan-456"

        # Verificar insights
        updated_insights = call_args.kwargs["updates"]["insights"]
        assert len(updated_insights) == 1
        assert updated_insights[0]["insight_id"] == "insight-123"
        assert "received_at" in updated_insights[0]

    @pytest.mark.asyncio()
    async def test_enrich_plan_without_mongodb(self, consumer):
        """Deve lidar gracefully com MongoDB indisponível."""
        consumer.mongodb_client = None

        insight = {"insight_id": "insight-123", "plan_id": "plan-456"}

        # Não deve lançar exceção
        await consumer._enrich_cognitive_plan(insight)


class TestStoreInsight:
    """Testes de armazenamento de insight."""

    @pytest.mark.asyncio()
    async def test_store_insight_in_mongodb(self, consumer, mock_mongodb_client):
        """Deve armazenar insight no MongoDB."""
        insight = {
            "insight_id": "insight-123",
            "insight_type": "PREDICTIVE",
            "priority": "HIGH",
            "description": "Test insight",
        }

        mock_mongodb_client.insert_insight = AsyncMock()

        await consumer._store_insight(insight)

        mock_mongodb_client.insert_insight.assert_called_once()
        call_args = mock_mongodb_client.insert_insight.call_args
        stored_insight = call_args[0][0]

        assert stored_insight["insight_id"] == "insight-123"
        assert "received_at" in stored_insight
        assert stored_insight["consumer"] == "orchestrator-dynamic"

    @pytest.mark.asyncio()
    async def test_store_without_mongodb(self, consumer):
        """Deve lidar gracefully com MongoDB indisponível."""
        consumer.mongodb_client = None

        insight = {"insight_id": "insight-123"}

        # Não deve lançar exceção
        await consumer._store_insight(insight)


class TestConsumerLifecycle:
    """Testes de ciclo de vida do consumer."""

    @pytest.mark.asyncio()
    async def test_start_stop_consumer(self, consumer):
        """Deve iniciar e parar consumer corretamente."""
        mock_consumer = AsyncMock()
        mock_consumer.start = AsyncMock()
        mock_consumer.stop = AsyncMock()

        # Criar um iterador assíncrono vazio
        async def async_iterator():
            return
            yield  # (falso positivo, é usado para gerar iterador vazio)

        mock_consumer.__aiter__ = lambda self: async_iterator()
        mock_consumer.commit = AsyncMock()

        with patch("src.consumers.insights_consumer.instrument_kafka_consumer") as mock_instrument:
            mock_instrument.return_value = mock_consumer

            await consumer.initialize()
            assert consumer.consumer is not None

            # Simular start (loop vazio)
            start_task = asyncio.create_task(consumer.start())
            await asyncio.sleep(0.05)
            consumer.running = False

            try:
                await asyncio.wait_for(start_task, timeout=0.1)
            except asyncio.TimeoutError:
                pass

            await consumer.stop()
            mock_consumer.stop.assert_called_once()


class TestErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio()
    async def test_error_handling_invalid_json(self, consumer, mock_mongodb_client):
        """Deve lidar com JSON inválido na mensagem."""
        message = MagicMock()
        message.value = b"{invalid json}"
        message.headers = []

        await consumer._process_message(message)

        # Não deve quebrar e não deve chamar MongoDB
        mock_mongodb_client.get_cognitive_plan.assert_not_called()
        mock_mongodb_client.insert_insight.assert_not_called()

    @pytest.mark.asyncio()
    async def test_error_handling_mongodb_unavailable(self, consumer):
        """Deve lidar com MongoDB indisponível."""
        insight_data = {
            "insight_id": "insight-123",
            "insight_type": "PREDICTIVE",
            "priority": "HIGH",
            "plan_id": "plan-456",
            "description": "Test insight",
        }

        message = MagicMock()
        message.value = json.dumps(insight_data).encode("utf-8")
        message.headers = []

        # MongoDB retorna erro
        consumer.mongodb_client = None

        # Não deve lançar exceção
        await consumer._process_message(message)


class TestMetricsTracking:
    """Testes de tracking de métricas."""

    @pytest.mark.asyncio()
    async def test_metrics_tracking_on_process(self, consumer, mock_mongodb_client, mock_metrics):
        """Deve atualizar métricas ao processar insight."""
        insight_data = {
            "insight_id": "insight-123",
            "insight_type": "PREDICTIVE",
            "priority": "HIGH",
            "plan_id": "plan-456",
            "description": "Test insight",
        }

        message = MagicMock()
        message.value = json.dumps(insight_data).encode("utf-8")
        message.headers = []

        mock_mongodb_client.get_cognitive_plan = AsyncMock(
            return_value={"plan_id": "plan-456", "status": "IN_PROGRESS", "insights": []}
        )
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_insight = AsyncMock()

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar métrica incrementada
        mock_metrics.insights_consumed_total.labels.assert_called()
        mock_metrics.insights_consumed_total.labels.return_value.inc.assert_called_once()
