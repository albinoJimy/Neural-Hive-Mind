"""
Unit tests para StrategicDecisionConsumer.

Testa o consumer que processa strategic.decisions do Queen Agent,
atualizando workflows e persistindo decisões para histórico.
"""
import pytest
import json
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Mock de dependências problemáticas antes de importar
sys.modules['neural_hive_security'] = MagicMock()
sys.modules['neural_hive_security.cors'] = MagicMock()

from src.consumers.strategic_decision_consumer import (
    StrategicDecisionConsumer,
    StrategicDecisionType
)


@pytest.fixture
def mock_config():
    """Config mock para testes."""
    config = MagicMock()
    config.kafka_bootstrap_servers = "localhost:9092"
    config.kafka_consumer_group_id = "test-group"
    config.kafka_strategic_topic = "strategic.decisions"
    config.kafka_security_protocol = "PLAINTEXT"
    return config


@pytest.fixture
def mock_mongodb_client():
    """MongoDB client mock."""
    mongodb = AsyncMock()
    mongodb.get_cognitive_plan = AsyncMock()
    mongodb.update_cognitive_plan = AsyncMock()
    mongodb.insert_strategic_decision = AsyncMock()
    return mongodb


@pytest.fixture
def mock_temporal_client():
    """Temporal client mock."""
    temporal = AsyncMock()
    temporal.cancel_workflow = AsyncMock()
    return temporal


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock()
    metrics.strategic_decisions_consumed_total = MagicMock()
    metrics.strategic_decisions_consumed_total.labels.return_value = MagicMock()
    metrics.strategic_decisions_consumed_total.labels.return_value.inc = MagicMock()
    return metrics


@pytest.fixture
def consumer(mock_config, mock_mongodb_client, mock_temporal_client, mock_metrics):
    """Consumer instance para testes."""
    return StrategicDecisionConsumer(
        config=mock_config,
        mongodb_client=mock_mongodb_client,
        temporal_client=mock_temporal_client,
        metrics=mock_metrics
    )


class TestStrategicDecisionConsumerInitialization:
    """Testes de inicialização do consumer."""

    def test_consumer_initialization(self, consumer):
        """Consumer deve ter atributos corretos após criação."""
        assert consumer.config is not None
        assert consumer.mongodb_client is not None
        assert consumer.temporal_client is not None
        assert consumer.metrics is not None
        assert consumer.consumer is None
        assert consumer.running is False

    @pytest.mark.asyncio
    async def test_consumer_initialize(self, consumer):
        """Consumer deve inicializar corretamente."""
        mock_producer = MagicMock()
        mock_producer.start = AsyncMock()

        with patch('src.consumers.strategic_decision_consumer.instrument_kafka_consumer') as mock_instrument:
            mock_instrument.return_value = mock_producer

            await consumer.initialize()

            assert consumer.consumer is not None
            mock_producer.start.assert_called_once()


class TestProcessMessage:
    """Testes de processamento de mensagens."""

    @pytest.mark.asyncio
    async def test_process_priority_change_decision(self, consumer, mock_mongodb_client):
        """Deve processar decisão de mudança de prioridade."""
        decision_data = {
            'decision_id': 'decision-123',
            'decision_type': StrategicDecisionType.PRIORITY_CHANGE.value,
            'plan_id': 'plan-456',
            'correlation_id': 'corr-789',
            'parameters': {
                'priority': 'CRITICAL'
            }
        }

        message = MagicMock()
        message.value = json.dumps(decision_data).encode('utf-8')
        message.headers = []
        message.topic = 'strategic.decisions'
        message.partition = 0
        message.offset = 0

        # Mock MongoDB
        mock_mongodb_client.get_cognitive_plan = AsyncMock(return_value={
            'plan_id': 'plan-456',
            'status': 'IN_PROGRESS'
        })
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_strategic_decision = AsyncMock()

        # Mock commit
        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar que o plano foi atualizado
        mock_mongodb_client.update_cognitive_plan.assert_called_once()
        call_args = mock_mongodb_client.update_cognitive_plan.call_args
        assert call_args.kwargs['plan_id'] == 'plan-456'
        assert call_args.kwargs['updates']['priority'] == 'CRITICAL'

    @pytest.mark.asyncio
    async def test_process_cancellation_decision(self, consumer, mock_mongodb_client, mock_temporal_client):
        """Deve processar decisão de cancelamento."""
        decision_data = {
            'decision_id': 'decision-123',
            'decision_type': StrategicDecisionType.CANCELLATION.value,
            'plan_id': 'plan-456',
            'parameters': {
                'reason': 'Strategic decision'
            }
        }

        message = MagicMock()
        message.value = json.dumps(decision_data).encode('utf-8')
        message.headers = []

        # Mock MongoDB retorna plano em progresso
        mock_mongodb_client.get_cognitive_plan = AsyncMock(return_value={
            'plan_id': 'plan-456',
            'status': 'IN_PROGRESS'
        })
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_strategic_decision = AsyncMock()

        # Mock commit
        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar que workflow foi cancelado
        mock_temporal_client.cancel_workflow.assert_called_once_with('orchestration-plan-456')

        # Verificar que plano foi atualizado
        mock_mongodb_client.update_cognitive_plan.assert_called_once()
        call_args = mock_mongodb_client.update_cognitive_plan.call_args
        assert call_args.kwargs['plan_id'] == 'plan-456'
        assert call_args.kwargs['updates']['status'] == 'CANCELLED'

    @pytest.mark.asyncio
    async def test_process_escalation_decision(self, consumer, mock_mongodb_client):
        """Deve processar decisão de escalada."""
        decision_data = {
            'decision_id': 'decision-123',
            'decision_type': StrategicDecisionType.ESCALATION.value,
            'plan_id': 'plan-456',
            'parameters': {
                'reason': 'Critical issue detected'
            }
        }

        message = MagicMock()
        message.value = json.dumps(decision_data).encode('utf-8')
        message.headers = []

        mock_mongodb_client.get_cognitive_plan = AsyncMock(return_value={
            'plan_id': 'plan-456',
            'status': 'IN_PROGRESS'
        })
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_strategic_decision = AsyncMock()

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar escalada
        mock_mongodb_client.update_cognitive_plan.assert_called_once()
        call_args = mock_mongodb_client.update_cognitive_plan.call_args
        assert call_args.kwargs['updates']['escalated'] is True
        assert call_args.kwargs['updates']['escalation_reason'] == 'Critical issue detected'

    @pytest.mark.asyncio
    async def test_skip_cancellation_of_completed_plan(self, consumer, mock_mongodb_client, mock_temporal_client):
        """Deve ignorar cancelamento de plano já completado."""
        decision_data = {
            'decision_id': 'decision-123',
            'decision_type': StrategicDecisionType.CANCELLATION.value,
            'plan_id': 'plan-456',
            'parameters': {}
        }

        message = MagicMock()
        message.value = json.dumps(decision_data).encode('utf-8')
        message.headers = []

        # Mock MongoDB retorna plano completado
        mock_mongodb_client.get_cognitive_plan = AsyncMock(return_value={
            'plan_id': 'plan-456',
            'status': 'COMPLETED'
        })
        mock_mongodb_client.update_cognitive_plan = AsyncMock()

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Não deve cancelar workflow já completado
        mock_temporal_client.cancel_workflow.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_workflow_adjustment(self, consumer, mock_mongodb_client):
        """Deve processar ajuste de workflow."""
        decision_data = {
            'decision_id': 'decision-123',
            'decision_type': StrategicDecisionType.WORKFLOW_ADJUSTMENT.value,
            'plan_id': 'plan-456',
            'parameters': {
                'adjustments': [
                    {'action': 'add_task', 'task_id': 'task-789'},
                    {'action': 'modify_param', 'param': 'timeout', 'value': 300}
                ]
            }
        }

        message = MagicMock()
        message.value = json.dumps(decision_data).encode('utf-8')
        message.headers = []

        mock_mongodb_client.get_cognitive_plan = AsyncMock(return_value={
            'plan_id': 'plan-456',
            'status': 'IN_PROGRESS',
            'workflow_adjustments': []
        })
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_strategic_decision = AsyncMock()

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar ajustes
        mock_mongodb_client.update_cognitive_plan.assert_called_once()
        call_args = mock_mongodb_client.update_cognitive_plan.call_args
        adjustments = call_args.kwargs['updates']['workflow_adjustments']
        assert len(adjustments) == 2

    @pytest.mark.asyncio
    async def test_process_resource_reallocation(self, consumer, mock_mongodb_client):
        """Deve processar realocação de recursos."""
        decision_data = {
            'decision_id': 'decision-123',
            'decision_type': StrategicDecisionType.RESOURCE_REALLOCATION.value,
            'plan_id': 'plan-456',
            'parameters': {
                'resources': {
                    'cpu': '4000m',
                    'memory': '8Gi',
                    'workers': 4
                }
            }
        }

        message = MagicMock()
        message.value = json.dumps(decision_data).encode('utf-8')
        message.headers = []

        mock_mongodb_client.get_cognitive_plan = AsyncMock(return_value={
            'plan_id': 'plan-456',
            'status': 'IN_PROGRESS'
        })
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_strategic_decision = AsyncMock()

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar realocação
        mock_mongodb_client.update_cognitive_plan.assert_called_once()
        call_args = mock_mongodb_client.update_cognitive_plan.call_args
        assert call_args.kwargs['updates']['resource_allocation']['cpu'] == '4000m'

    @pytest.mark.asyncio
    async def test_process_policy_update(self, consumer, mock_mongodb_client):
        """Deve processar atualização de políticas."""
        decision_data = {
            'decision_id': 'decision-123',
            'decision_type': StrategicDecisionType.POLICY_UPDATE.value,
            'plan_id': 'plan-456',
            'parameters': {
                'policies': {
                    'retry_policy': 'exponential_backoff',
                    'timeout': 300
                }
            }
        }

        message = MagicMock()
        message.value = json.dumps(decision_data).encode('utf-8')
        message.headers = []

        mock_mongodb_client.get_cognitive_plan = AsyncMock(return_value={
            'plan_id': 'plan-456',
            'status': 'IN_PROGRESS'
        })
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_strategic_decision = AsyncMock()

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar políticas
        mock_mongodb_client.update_cognitive_plan.assert_called_once()
        call_args = mock_mongodb_client.update_cognitive_plan.call_args
        assert call_args.kwargs['updates']['policies']['retry_policy'] == 'exponential_backoff'


class TestStoreDecision:
    """Testes de armazenamento de decisão."""

    @pytest.mark.asyncio
    async def test_store_decision_in_mongodb(self, consumer, mock_mongodb_client):
        """Deve armazenar decisão no MongoDB."""
        decision = {
            'decision_id': 'decision-123',
            'decision_type': 'PRIORITY_CHANGE',
            'plan_id': 'plan-456'
        }

        await consumer._store_decision(decision)

        mock_mongodb_client.insert_strategic_decision.assert_called_once()
        call_args = mock_mongodb_client.insert_strategic_decision.call_args
        stored_decision = call_args[0][0]

        assert stored_decision['decision_id'] == 'decision-123'
        assert 'received_at' in stored_decision
        assert stored_decision['consumer'] == 'orchestrator-dynamic'

    @pytest.mark.asyncio
    async def test_store_without_mongodb(self, consumer):
        """Deve lidar gracefully com MongoDB indisponível."""
        consumer.mongodb_client = None

        decision = {'decision_id': 'decision-123'}

        # Não deve lançar exceção
        await consumer._store_decision(decision)


class TestConsumerLifecycle:
    """Testes de ciclo de vida do consumer."""

    @pytest.mark.asyncio
    async def test_start_stop_consumer(self, consumer):
        """Deve iniciar e parar consumer corretamente."""
        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer.stop = AsyncMock()

        # Criar um iterador assíncrono vazio
        async def async_iterator():
            return
            yield

        mock_producer.__aiter__ = lambda self: async_iterator()
        mock_producer.commit = AsyncMock()

        with patch('src.consumers.strategic_decision_consumer.instrument_kafka_consumer') as mock_instrument:
            mock_instrument.return_value = mock_producer

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
            mock_producer.stop.assert_called_once()


class TestErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_error_handling_invalid_json(self, consumer, mock_mongodb_client):
        """Deve lidar com JSON inválido na mensagem."""
        message = MagicMock()
        message.value = b'{invalid json}'
        message.headers = []

        await consumer._process_message(message)

        # Não deve quebrar e não deve chamar MongoDB
        mock_mongodb_client.get_cognitive_plan.assert_not_called()
        mock_mongodb_client.update_cognitive_plan.assert_not_called()
        mock_mongodb_client.insert_strategic_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_recovery_on_mongodb_failure(self, consumer, mock_mongodb_client):
        """Deve recuperar de falha no MongoDB."""
        decision_data = {
            'decision_id': 'decision-123',
            'decision_type': StrategicDecisionType.PRIORITY_CHANGE.value,
            'plan_id': 'plan-456',
            'parameters': {'priority': 'CRITICAL'}
        }

        message = MagicMock()
        message.value = json.dumps(decision_data).encode('utf-8')
        message.headers = []

        # MongoDB lança exceção
        mock_mongodb_client.get_cognitive_plan = AsyncMock(side_effect=Exception("DB unavailable"))
        mock_mongodb_client.insert_strategic_decision = AsyncMock()

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        # Não deve lançar exceção
        await consumer._process_message(message)


class TestMetricsTracking:
    """Testes de tracking de métricas."""

    @pytest.mark.asyncio
    async def test_metrics_tracking_on_process(self, consumer, mock_mongodb_client, mock_metrics):
        """Deve atualizar métricas ao processar decisão."""
        decision_data = {
            'decision_id': 'decision-123',
            'decision_type': StrategicDecisionType.PRIORITY_CHANGE.value,
            'plan_id': 'plan-456',
            'correlation_id': 'corr-789',
            'parameters': {'priority': 'CRITICAL'}
        }

        message = MagicMock()
        message.value = json.dumps(decision_data).encode('utf-8')
        message.headers = []

        mock_mongodb_client.get_cognitive_plan = AsyncMock(return_value={
            'plan_id': 'plan-456',
            'status': 'IN_PROGRESS'
        })
        mock_mongodb_client.update_cognitive_plan = AsyncMock()
        mock_mongodb_client.insert_strategic_decision = AsyncMock()

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar métrica incrementada
        mock_metrics.strategic_decisions_consumed_total.labels.assert_called()
        mock_metrics.strategic_decisions_consumed_total.labels.return_value.inc.assert_called_once()
